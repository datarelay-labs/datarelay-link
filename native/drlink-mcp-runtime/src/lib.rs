//! Bounded MCP dispatch admission primitive.
//!
//! Python remains responsible for authentication, AI Access, durable jobs,
//! audit and the dispatch itself. This library only tracks an in-process cap.
use std::sync::atomic::{AtomicUsize, Ordering};
use std::collections::VecDeque;
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

#[repr(C)]
pub struct DispatchBudget {
    capacity: usize,
    inflight: AtomicUsize,
}

type OutputChunk = extern "C" fn(i32, *const u8, usize, *mut std::ffi::c_void) -> bool;
type WriteChunk = extern "C" fn(*const u8, usize, *mut std::ffi::c_void) -> isize;
type ReadChunk = extern "C" fn(*mut u8, usize, *mut std::ffi::c_void) -> isize;

pub struct WaitSignal {
    generation: Mutex<u64>,
    changed: Condvar,
}

/// Create a bounded notification signal for one Python-owned DB subscription.
/// Database polling, job state, and result consumption remain in Python.
#[no_mangle]
pub extern "C" fn drlink_mcp_wait_signal_new() -> *mut Arc<WaitSignal> {
    Box::into_raw(Box::new(Arc::new(WaitSignal {
        generation: Mutex::new(0),
        changed: Condvar::new(),
    })))
}

/// Read the current signal generation before the caller checks SQLite.
///
/// # Safety
/// `handle` must be null or a live pointer returned by
/// `drlink_mcp_wait_signal_new`, with no concurrent free.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_wait_signal_snapshot(
    handle: *const Arc<WaitSignal>,
) -> u64 {
    match handle.as_ref().and_then(|signal| signal.generation.lock().ok()) {
        Some(generation) => *generation,
        None => u64::MAX,
    }
}

/// Wake waiters after Python's DB watcher reports a relevant committed change.
///
/// # Safety
/// `handle` must be null or a live pointer returned by
/// `drlink_mcp_wait_signal_new`, with no concurrent free.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_wait_signal_notify(
    handle: *const Arc<WaitSignal>,
) -> i32 {
    let Some(signal) = handle.as_ref() else { return 0 };
    let Ok(mut generation) = signal.generation.lock() else { return 0 };
    *generation = generation.wrapping_add(1);
    signal.changed.notify_all();
    1
}

/// Clone the signal's Arc before waiting so Python may close the subscription.
///
/// # Safety
/// `handle` must be null or a live pointer returned by
/// `drlink_mcp_wait_signal_new`, with no concurrent free.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_wait_signal_ticket_new(
    handle: *const Arc<WaitSignal>,
) -> *mut Arc<WaitSignal> {
    match handle.as_ref() {
        Some(signal) => Box::into_raw(Box::new(Arc::clone(signal))),
        None => std::ptr::null_mut(),
    }
}

/// Wait for a generation change, releasing the Rust lock while blocked.
///
/// # Safety
/// `ticket` must be null or a live pointer returned by
/// `drlink_mcp_wait_signal_ticket_new`, with no concurrent free.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_wait_signal_ticket_wait(
    ticket: *const Arc<WaitSignal>,
    observed: u64,
    timeout_ms: u64,
) -> i32 {
    let Some(signal) = ticket.as_ref() else { return -1 };
    let Ok(generation) = signal.generation.lock() else { return -1 };
    if *generation != observed { return 1; }
    let Ok((generation, _)) = signal.changed.wait_timeout_while(
        generation,
        Duration::from_millis(timeout_ms),
        |generation| *generation == observed,
    ) else { return -1 };
    if *generation != observed { 1 } else { 0 }
}

/// Release one independent wait ticket.
///
/// # Safety
/// `ticket` must be null or a live pointer returned by
/// `drlink_mcp_wait_signal_ticket_new`, and must be freed exactly once.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_wait_signal_ticket_free(
    ticket: *mut Arc<WaitSignal>,
) {
    if !ticket.is_null() { drop(Box::from_raw(ticket)); }
}

/// Release the subscription's owning reference; active tickets remain valid.
///
/// # Safety
/// `handle` must be null or a live pointer returned by
/// `drlink_mcp_wait_signal_new`, and must be freed exactly once.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_wait_signal_free(handle: *mut Arc<WaitSignal>) {
    if !handle.is_null() { drop(Box::from_raw(handle)); }
}

/// Accept one connection from a Python-owned, already-ready listener.
/// The listener bind/backlog and connection/TLS authority stay in Python.
/// Returns an accepted close-on-exec fd or the negated errno.
#[no_mangle]
pub extern "C" fn drlink_mcp_accept(listener_fd: libc::c_int) -> libc::c_int {
    if listener_fd < 0 {
        return -libc::EBADF;
    }
    #[cfg(target_os = "linux")]
    let accepted = unsafe {
        libc::accept4(
            listener_fd,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            libc::SOCK_CLOEXEC,
        )
    };
    #[cfg(target_os = "macos")]
    let accepted = unsafe {
        let fd = libc::accept(listener_fd, std::ptr::null_mut(), std::ptr::null_mut());
        if fd >= 0 && libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC) < 0 {
            let error = *libc::__error();
            libc::close(fd);
            return -error;
        }
        fd
    };
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    let accepted = { let _ = listener_fd; return -libc::ENOSYS; };
    if accepted >= 0 {
        accepted
    } else {
        #[cfg(target_os = "macos")]
        let error = unsafe { *libc::__error() };
        #[cfg(not(target_os = "macos"))]
        let error = unsafe { *libc::__errno_location() };
        -error
    }
}

/// Create a persistent macOS process-exit watcher. Python owns its lifetime
/// across timeout/retry drain calls and closes it after final EOF or failure.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_process_watch_new(pid: libc::pid_t) -> libc::c_int {
    #[cfg(target_os = "macos")]
    {
        if pid <= 0 { return -1; }
        let queue = libc::kqueue();
        if queue < 0 { return -1; }
        let mut change: libc::kevent = std::mem::zeroed();
        change.ident = pid as libc::uintptr_t;
        change.filter = libc::EVFILT_PROC;
        // Install NOTE_EXIT once; the stateful drain API carries the observed
        // exit across calls because kqueue delivers this process event once.
        change.flags = (libc::EV_ADD | libc::EV_ENABLE) as u16;
        change.fflags = libc::NOTE_EXIT;
        if libc::kevent(queue, &change, 1, std::ptr::null_mut(), 0, std::ptr::null()) < 0 {
            libc::close(queue);
            return -1;
        }
        queue
    }
    #[cfg(not(target_os = "macos"))]
    { let _ = pid; -1 }
}

#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_process_watch_free(queue: libc::c_int) {
    #[cfg(target_os = "macos")]
    if queue >= 0 { libc::close(queue); }
    #[cfg(not(target_os = "macos"))]
    let _ = queue;
}

struct OutputState {
    bytes: VecDeque<u8>,
    dropped: u64,
    total: u64,
}

pub struct BoundedOutput {
    capacity: usize,
    state: Mutex<OutputState>,
}

/// Create a budget. Invalid capacities return null and fail closed at caller.
#[no_mangle]
pub extern "C" fn drlink_mcp_budget_new(capacity: usize) -> *mut DispatchBudget {
    if capacity == 0 {
        return std::ptr::null_mut();
    }
    Box::into_raw(Box::new(DispatchBudget {
        capacity,
        inflight: AtomicUsize::new(0),
    }))
}

/// Atomically take one slot without waiting. Returns 1 if admitted, else 0.
///
/// # Safety
/// `budget` must be null or point to a live value returned by
/// `drlink_mcp_budget_new`; it must not be freed concurrently.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_budget_try_acquire(
    budget: *mut DispatchBudget,
) -> i32 {
    let Some(budget) = budget.as_ref() else { return 0 };
    let mut current = budget.inflight.load(Ordering::Relaxed);
    loop {
        if current >= budget.capacity {
            return 0;
        }
        match budget.inflight.compare_exchange_weak(
            current,
            current + 1,
            Ordering::AcqRel,
            Ordering::Relaxed,
        ) {
            Ok(_) => return 1,
            Err(actual) => current = actual,
        }
    }
}

/// Release one previously acquired slot; extra releases are ignored.
///
/// # Safety
/// `budget` must be null or point to a live value returned by
/// `drlink_mcp_budget_new`; it must not be freed concurrently.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_budget_release(budget: *mut DispatchBudget) {
    let Some(budget) = budget.as_ref() else { return };
    let mut current = budget.inflight.load(Ordering::Relaxed);
    while current > 0 {
        match budget.inflight.compare_exchange_weak(
            current,
            current - 1,
            Ordering::AcqRel,
            Ordering::Relaxed,
        ) {
            Ok(_) => return,
            Err(actual) => current = actual,
        }
    }
}

/// Free a budget after all users have stopped. Concurrent use during free is invalid.
///
/// # Safety
/// `budget` must be null or a live pointer returned by
/// `drlink_mcp_budget_new`, and no thread may use it again after this call.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_budget_free(budget: *mut DispatchBudget) {
    if !budget.is_null() {
        drop(Box::from_raw(budget));
    }
}

/// Create a fixed-capacity byte window for a streamed MCP job result.
#[no_mangle]
pub extern "C" fn drlink_mcp_output_new(capacity: usize) -> *mut BoundedOutput {
    if capacity == 0 || capacity > 16 * 1024 * 1024 {
        return std::ptr::null_mut();
    }
    Box::into_raw(Box::new(BoundedOutput {
        capacity,
        state: Mutex::new(OutputState {
            bytes: VecDeque::with_capacity(capacity),
            dropped: 0,
            total: 0,
        }),
    }))
}

/// Append output while retaining only the newest `capacity` bytes.
/// Returns 1 on success and 0 for invalid arguments, overflow or poisoned state.
///
/// # Safety
/// `output` must be a live handle from `drlink_mcp_output_new`; `data` must
/// reference `len` readable bytes for the duration of this call.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_output_append(
    output: *mut BoundedOutput,
    data: *const u8,
    len: usize,
) -> i32 {
    let Some(output) = output.as_ref() else { return 0 };
    if len > 0 && data.is_null() {
        return 0;
    }
    let Ok(mut state) = output.state.lock() else { return 0 };
    let Some(total) = state.total.checked_add(len as u64) else { return 0 };
    if len == 0 {
        return 1;
    }
    let dropped = if len > output.capacity {
        let old_len = state.bytes.len();
        state.bytes.clear();
        let skip = len - output.capacity;
        state.bytes.extend(std::slice::from_raw_parts(data.add(skip), output.capacity));
        state.dropped.saturating_add(old_len as u64 + skip as u64)
    } else {
        state.bytes.extend(std::slice::from_raw_parts(data, len));
        let excess = state.bytes.len().saturating_sub(output.capacity);
        for _ in 0..excess { state.bytes.pop_front(); }
        state.dropped.saturating_add(excess as u64)
    };
    state.total = total;
    state.dropped = dropped;
    1
}

/// Copy one bounded page using the existing cursor/eviction semantics.
/// Returns 1 on success and 0 for invalid arguments or poisoned state.
///
/// # Safety
/// `output` must be a live handle; `buffer` must reference `buffer_capacity`
/// writable bytes, and all output pointers must be writable.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_output_page(
    output: *mut BoundedOutput,
    cursor: u64,
    page_limit: usize,
    buffer: *mut u8,
    buffer_capacity: usize,
    written: *mut usize,
    next_cursor: *mut u64,
    total: *mut u64,
    dropped: *mut u64,
    cursor_was_evicted: *mut bool,
) -> i32 {
    let Some(output) = output.as_ref() else { return 0 };
    if page_limit > buffer_capacity || (page_limit > 0 && buffer.is_null())
        || written.is_null() || next_cursor.is_null() || total.is_null()
        || dropped.is_null() || cursor_was_evicted.is_null()
    {
        return 0;
    }
    let Ok(state) = output.state.lock() else { return 0 };
    let start = cursor.max(state.dropped).min(state.total);
    let offset = (start - state.dropped) as usize;
    let count = page_limit.min(state.bytes.len().saturating_sub(offset));
    for (index, byte) in state.bytes.iter().skip(offset).take(count).enumerate() {
        *buffer.add(index) = *byte;
    }
    *written = count;
    *next_cursor = start.saturating_add(count as u64);
    *total = state.total;
    *dropped = state.dropped;
    *cursor_was_evicted = cursor < state.dropped;
    1
}

/// Free a bounded stream window after all readers have stopped.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_output_free(output: *mut BoundedOutput) {
    if !output.is_null() {
        drop(Box::from_raw(output));
    }
}

/// Write an already-framed MCP response body in bounded chunks through the
/// caller's socket/TLS writer. The callback owns the actual connection and
/// may return short writes; zero, negative, or over-reported writes fail.
///
/// # Safety
/// `data` must reference `len` readable bytes and `callback` must remain valid
/// for the duration of this call. `context` is passed through unchanged.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_write_chunks(
    data: *const u8,
    len: usize,
    chunk_limit: usize,
    callback: Option<WriteChunk>,
    context: *mut std::ffi::c_void,
) -> i32 {
    if (len > 0 && data.is_null()) || chunk_limit == 0 || chunk_limit > 64 * 1024 {
        return 0;
    }
    let Some(callback) = callback else { return 0 };
    let mut offset = 0usize;
    while offset < len {
        let end = offset.saturating_add(chunk_limit).min(len);
        let mut written = offset;
        while written < end {
            let remaining = end - written;
            let count = callback(data.add(written), remaining, context);
            if count <= 0 || count as usize > remaining {
                return 0;
            }
            written += count as usize;
        }
        offset = end;
    }
    1
}

/// Read exactly one bounded HTTP request body through the caller-owned reader.
/// Python retains socket/TLS ownership; this helper limits native read chunks
/// and refuses bodies above the public 2 MB request limit.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_read_request_body(
    output: *mut u8,
    len: usize,
    callback: Option<ReadChunk>,
    context: *mut std::ffi::c_void,
) -> i32 {
    const BODY_LIMIT: usize = 2_000_000;
    const CHUNK_LIMIT: usize = 64 * 1024;
    if len > BODY_LIMIT || (len > 0 && output.is_null()) {
        return 0;
    }
    if len == 0 {
        return 1;
    }
    let Some(callback) = callback else { return 0 };
    let mut offset = 0usize;
    while offset < len {
        let capacity = (len - offset).min(CHUNK_LIMIT);
        let count = callback(output.add(offset), capacity, context);
        if count <= 0 || count as usize > capacity {
            return 0;
        }
        offset += count as usize;
    }
    1
}

/// Drain a spawned child's stdout/stderr while observing its exit without
/// reaping it. Python retains process creation, termination policy and reaping.
/// Return 0 after the leader exits and currently available pipe bytes are
/// drained, 1 on timeout, 2 on OS error, 3 if the output callback refuses data.
/// A zero timeout means wait without a deadline. The caller can then terminate
/// remaining process-group children and call again to drain pipes to EOF.
///
/// # Safety
/// `pid` must identify a live child owned by the caller; both descriptors must
/// be open read ends that remain valid for this call. `callback` must be valid.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_drain_child_stateful(
    pid: libc::pid_t,
    stdout_fd: libc::c_int,
    stderr_fd: libc::c_int,
    _process_watch_fd: libc::c_int,
    timeout_ms: u64,
    wait_for_eof: bool,
    leader_exited: *mut bool,
    callback: Option<OutputChunk>,
    context: *mut std::ffi::c_void,
) -> i32 {
    if pid <= 0 || stdout_fd < 0 || stderr_fd < 0 || callback.is_none() {
        return 2;
    }
    let callback = callback.unwrap();
    let started = Instant::now();
    let timeout = Duration::from_millis(timeout_ms);
    let mut exited = if leader_exited.is_null() { false } else { *leader_exited };

    // waitid(WNOWAIT) is not part of Apple's documented wait API. Observe
    // NOTE_EXIT through kqueue instead, leaving wait/reap ownership in Python.
    #[cfg(target_os = "macos")]
    if _process_watch_fd < 0 { return 4; }
    let mut stdout_open = true;
    let mut stderr_open = true;
    let mut buffer = [0u8; 8192];

    loop {
        #[cfg(target_os = "linux")]
        if !exited {
            let mut info: libc::siginfo_t = std::mem::zeroed();
            let result = libc::waitid(
                libc::P_PID,
                pid as libc::id_t,
                &mut info,
                libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            );
            if result == 0 {
                exited = info.si_pid() != 0;
                if exited && !leader_exited.is_null() { *leader_exited = true; }
            } else {
                let error = std::io::Error::last_os_error();
                if error.kind() != std::io::ErrorKind::Interrupted {
                    return 6;
                }
            }
        }
        #[cfg(target_os = "macos")]
        if !exited {
            let mut event: libc::kevent = std::mem::zeroed();
            let no_wait = libc::timespec { tv_sec: 0, tv_nsec: 0 };
            let result = libc::kevent(
                _process_watch_fd,
                std::ptr::null(),
                0,
                &mut event,
                1,
                &no_wait,
            );
            if result == 1 {
                if event.fflags & libc::NOTE_EXIT != 0 {
                    exited = true;
                    if !leader_exited.is_null() { *leader_exited = true; }
                } else if event.flags & libc::EV_ERROR != 0 {
                    return 2;
                }
            } else if result < 0 {
                let error = std::io::Error::last_os_error();
                if error.kind() != std::io::ErrorKind::Interrupted {
                    return 2;
                }
            }
        }
        if exited && !stdout_open && !stderr_open {
            return 0;
        }
        if timeout_ms > 0 && started.elapsed() >= timeout {
            return 1;
        }

        let mut fds = [
            libc::pollfd {
                fd: if stdout_open { stdout_fd } else { -1 },
                events: (libc::POLLIN | libc::POLLHUP) as i16,
                revents: 0,
            },
            libc::pollfd {
                fd: if stderr_open { stderr_fd } else { -1 },
                events: (libc::POLLIN | libc::POLLHUP) as i16,
                revents: 0,
            },
        ];
        let result = libc::poll(
            fds.as_mut_ptr(),
            fds.len() as libc::nfds_t,
            if exited && !wait_for_eof { 0 } else { 10 },
        );
        if result < 0 {
            let error = std::io::Error::last_os_error();
            if error.kind() == std::io::ErrorKind::Interrupted {
                continue;
            }
            return 7;
        }
        if result == 0 && exited && !wait_for_eof {
            return 9;
        }
        for index in 0..2 {
            if fds[index].revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
                return 2;
            }
            if fds[index].revents & (libc::POLLIN | libc::POLLHUP) == 0 {
                continue;
            }
            let fd = fds[index].fd;
            let count = libc::read(fd, buffer.as_mut_ptr().cast(), buffer.len());
            if count == 0 {
                if index == 0 { stdout_open = false; } else { stderr_open = false; }
            } else if count < 0 {
                let error = std::io::Error::last_os_error();
                if error.kind() != std::io::ErrorKind::WouldBlock
                    && error.kind() != std::io::ErrorKind::Interrupted
                {
                    return 8;
                }
            } else if !callback(index as i32 + 1, buffer.as_ptr(), count as usize, context) {
                return 3;
            }
        }
        // Keep draining while either pipe remains immediately readable after
        // the leader exits. A normal child can leave more than one buffer of
        // output behind; treating the first partial read as descendant-held
        // would incorrectly return status 9 before reaching EOF. The zero
        // timeout poll above returns 9 only after buffered output is drained
        // and a pipe still has no EOF, which is the inherited-pipe case that
        // Python must clean up at process-group scope.
    }
}

/// Backward-compatible entry point for callers without persistent exit state.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_drain_child(
    pid: libc::pid_t,
    stdout_fd: libc::c_int,
    stderr_fd: libc::c_int,
    process_watch_fd: libc::c_int,
    timeout_ms: u64,
    wait_for_eof: bool,
    callback: Option<OutputChunk>,
    context: *mut std::ffi::c_void,
) -> i32 {
    drlink_mcp_drain_child_stateful(
        pid, stdout_fd, stderr_fd, process_watch_fd, timeout_ms, wait_for_eof,
        std::ptr::null_mut(), callback, context,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn admission_is_bounded_and_release_restores_capacity() {
        let budget = drlink_mcp_budget_new(2);
        unsafe {
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 0);
            drlink_mcp_budget_release(budget);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            drlink_mcp_budget_release(budget);
            drlink_mcp_budget_release(budget);
            drlink_mcp_budget_release(budget);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            drlink_mcp_budget_free(budget);
        }
    }

    #[test]
    fn invalid_capacity_fails_closed() {
        assert!(drlink_mcp_budget_new(0).is_null());
    }

    #[test]
    fn output_window_evicts_old_bytes_and_preserves_cursor_semantics() {
        let output = drlink_mcp_output_new(8);
        assert!(!output.is_null());
        unsafe {
            assert_eq!(drlink_mcp_output_append(output, b"abcde".as_ptr(), 5), 1);
            assert_eq!(drlink_mcp_output_append(output, b"FGHIJKLMNO".as_ptr(), 10), 1);
            let mut buffer = [0u8; 4];
            let mut written = 0usize;
            let mut next = 0u64;
            let mut total = 0u64;
            let mut dropped = 0u64;
            let mut evicted = false;
            assert_eq!(drlink_mcp_output_page(
                output, 0, 4, buffer.as_mut_ptr(), buffer.len(),
                &mut written, &mut next, &mut total, &mut dropped, &mut evicted,
            ), 1);
            assert_eq!(&buffer[..written], b"HIJK");
            assert_eq!((next, total, dropped, evicted), (11, 15, 7, true));
            assert_eq!(drlink_mcp_output_page(
                output, next, 4, buffer.as_mut_ptr(), buffer.len(),
                &mut written, &mut next, &mut total, &mut dropped, &mut evicted,
            ), 1);
            assert_eq!(&buffer[..written], b"LMNO");
            assert_eq!((next, total, dropped, evicted), (15, 15, 7, false));
            drlink_mcp_output_free(output);
        }
    }

    #[test]
    fn response_writer_bounds_chunks_and_retries_short_writes() {
        struct Sink {
            bytes: Vec<u8>,
            largest_chunk: usize,
        }
        extern "C" fn write_short(data: *const u8, len: usize, context: *mut std::ffi::c_void) -> isize {
            let sink = unsafe { &mut *(context as *mut Sink) };
            let count = len.min(7);
            sink.largest_chunk = sink.largest_chunk.max(len);
            sink.bytes.extend_from_slice(unsafe { std::slice::from_raw_parts(data, count) });
            count as isize
        }

        let input: Vec<u8> = (0..200_000).map(|i| (i % 251) as u8).collect();
        let mut sink = Sink { bytes: Vec::new(), largest_chunk: 0 };
        unsafe {
            assert_eq!(drlink_mcp_write_chunks(
                input.as_ptr(), input.len(), 64 * 1024, Some(write_short),
                (&mut sink as *mut Sink).cast(),
            ), 1);
        }
        assert_eq!(sink.bytes, input);
        assert_eq!(sink.largest_chunk, 64 * 1024);
    }

    #[test]
    fn response_writer_rejects_invalid_bounds_and_stalled_writes() {
        extern "C" fn stalled(_data: *const u8, _len: usize, _context: *mut std::ffi::c_void) -> isize { 0 }
        let input = b"response";
        unsafe {
            assert_eq!(drlink_mcp_write_chunks(input.as_ptr(), input.len(), 0, Some(stalled), std::ptr::null_mut()), 0);
            assert_eq!(drlink_mcp_write_chunks(input.as_ptr(), input.len(), 64 * 1024 + 1, Some(stalled), std::ptr::null_mut()), 0);
            assert_eq!(drlink_mcp_write_chunks(input.as_ptr(), input.len(), 8, Some(stalled), std::ptr::null_mut()), 0);
        }
    }

    #[test]
    fn request_reader_bounds_chunks_and_retries_short_reads() {
        struct Source { bytes: Vec<u8>, offset: usize, largest_chunk: usize }
        extern "C" fn read_short(target: *mut u8, capacity: usize, context: *mut std::ffi::c_void) -> isize {
            let source = unsafe { &mut *(context as *mut Source) };
            source.largest_chunk = source.largest_chunk.max(capacity);
            let count = capacity.min(7).min(source.bytes.len().saturating_sub(source.offset));
            if count == 0 { return 0; }
            unsafe { std::ptr::copy_nonoverlapping(source.bytes.as_ptr().add(source.offset), target, count); }
            source.offset += count;
            count as isize
        }

        let input: Vec<u8> = (0..200_000).map(|i| (i % 251) as u8).collect();
        let mut output = vec![0; input.len()];
        let mut source = Source { bytes: input.clone(), offset: 0, largest_chunk: 0 };
        unsafe {
            assert_eq!(drlink_mcp_read_request_body(
                output.as_mut_ptr(), output.len(), Some(read_short),
                (&mut source as *mut Source).cast(),
            ), 1);
        }
        assert_eq!(output, input);
        assert_eq!(source.offset, input.len());
        assert_eq!(source.largest_chunk, 64 * 1024);
    }

    #[test]
    fn request_reader_fails_closed_on_oversize_or_early_eof() {
        extern "C" fn empty(_target: *mut u8, _capacity: usize, _context: *mut std::ffi::c_void) -> isize { 0 }
        let mut output = [0u8; 4];
        unsafe {
            assert_eq!(drlink_mcp_read_request_body(
                output.as_mut_ptr(), 4, Some(empty), std::ptr::null_mut(),
            ), 0);
            assert_eq!(drlink_mcp_read_request_body(
                output.as_mut_ptr(), 2_000_001, Some(empty), std::ptr::null_mut(),
            ), 0);
        }
    }
}
