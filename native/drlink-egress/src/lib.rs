//! Bounded native bidirectional socket relay exposed to the existing Python
//! Internet Access policy/runtime authority through a narrow C ABI.
//!
//! The caller owns and closes both descriptors. `reauthorize` is invoked on a
//! fixed interval; false or a callback failure closes the stream fail-closed.
use libc::{c_int, c_void, pollfd};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::time::{Duration, Instant};

const MAX_BUFFER: usize = 256 * 1024;
const CHUNK: usize = 64 * 1024;
const CLIENT_CLOSED: c_int = 0;
const UPSTREAM_CLOSED: c_int = 1;
const IDLE_TIMEOUT: c_int = 2;
const POLICY_REVOKED: c_int = 3;
const IO_ERROR: c_int = 4;

type Reauthorize = extern "C" fn(*mut c_void) -> bool;

struct Buffer {
    bytes: Vec<u8>,
    offset: usize,
}

impl Buffer {
    fn new() -> Self { Self { bytes: Vec::with_capacity(MAX_BUFFER), offset: 0 } }
    fn len(&self) -> usize { self.bytes.len() - self.offset }
    fn is_empty(&self) -> bool { self.len() == 0 }
    fn available(&self) -> usize { MAX_BUFFER - self.len() }
    fn pending(&self) -> &[u8] { &self.bytes[self.offset..] }
    fn push(&mut self, data: &[u8]) {
        self.compact();
        self.bytes.extend_from_slice(data);
    }
    fn consume(&mut self, count: usize) {
        self.offset += count;
        if self.offset == self.bytes.len() { self.bytes.clear(); self.offset = 0; }
    }
    fn compact(&mut self) {
        if self.offset == self.bytes.len() { self.bytes.clear(); self.offset = 0; }
        else if self.offset > 0 { self.bytes.drain(..self.offset); self.offset = 0; }
    }
}

fn relay(
    client: c_int,
    upstream: c_int,
    revalidate: Duration,
    idle: Duration,
    callback: Reauthorize,
    context: *mut c_void,
    up_total: &mut u64,
    down_total: &mut u64,
) -> c_int {
    let mut c2u = Buffer::new();
    let mut u2c = Buffer::new();
    let (mut cr, mut ur, mut cw, mut uw) = (true, true, true, true);
    let mut last_data = Instant::now();
    let mut next_check = last_data + revalidate;
    let mut outcome = CLIENT_CLOSED;
    let mut cbuf = vec![0u8; CHUNK];
    let mut ubuf = vec![0u8; CHUNK];

    loop {
        if !cr && !ur && c2u.is_empty() && u2c.is_empty() { return outcome; }
        let now = Instant::now();
        if now.saturating_duration_since(last_data) >= idle { return IDLE_TIMEOUT; }
        if now >= next_check {
            next_check = now + revalidate;
            let allowed = catch_unwind(AssertUnwindSafe(|| callback(context))).unwrap_or(false);
            if !allowed { return POLICY_REVOKED; }
        }

        let mut c_events = 0;
        let mut u_events = 0;
        if cr && c2u.available() > 0 { c_events |= libc::POLLIN; }
        if cw && !u2c.is_empty() { c_events |= libc::POLLOUT; }
        if ur && u2c.available() > 0 { u_events |= libc::POLLIN; }
        if uw && !c2u.is_empty() { u_events |= libc::POLLOUT; }
        let until_check = next_check.saturating_duration_since(now);
        let until_idle = idle.saturating_sub(now.saturating_duration_since(last_data));
        let wait = until_check.min(until_idle).min(Duration::from_secs(1));
        let millis = wait.as_millis().min(i32::MAX as u128) as i32;
        let mut fds = [
            pollfd { fd: if c_events == 0 { -1 } else { client }, events: c_events as i16, revents: 0 },
            pollfd { fd: if u_events == 0 { -1 } else { upstream }, events: u_events as i16, revents: 0 },
        ];
        let ready = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as _, millis) };
        if ready < 0 {
            let error = std::io::Error::last_os_error();
            if error.kind() == std::io::ErrorKind::Interrupted { continue; }
            return IO_ERROR;
        }
        if ready == 0 { continue; }
        if fds.iter().any(|fd| fd.revents & (libc::POLLERR | libc::POLLNVAL) != 0) { return IO_ERROR; }

        if fds[0].revents & (libc::POLLIN | libc::POLLHUP) != 0 && cr {
            let cap = cbuf.len().min(c2u.available());
            if cap > 0 {
                let n = unsafe { libc::recv(client, cbuf.as_mut_ptr().cast(), cap, 0) };
                if n == 0 { cr = false; }
                else if n < 0 {
                    let e = std::io::Error::last_os_error();
                    if e.kind() != std::io::ErrorKind::WouldBlock && e.kind() != std::io::ErrorKind::Interrupted { return IO_ERROR; }
                } else { c2u.push(&cbuf[..n as usize]); last_data = Instant::now(); }
            }
        }
        if fds[1].revents & (libc::POLLIN | libc::POLLHUP) != 0 && ur {
            let cap = ubuf.len().min(u2c.available());
            if cap > 0 {
                let n = unsafe { libc::recv(upstream, ubuf.as_mut_ptr().cast(), cap, 0) };
                if n == 0 { ur = false; outcome = UPSTREAM_CLOSED; }
                else if n < 0 {
                    let e = std::io::Error::last_os_error();
                    if e.kind() != std::io::ErrorKind::WouldBlock && e.kind() != std::io::ErrorKind::Interrupted { return IO_ERROR; }
                } else { u2c.push(&ubuf[..n as usize]); last_data = Instant::now(); }
            }
        }
        if fds[1].revents & libc::POLLOUT != 0 && uw && !c2u.is_empty() {
            let n = unsafe { libc::send(upstream, c2u.pending().as_ptr().cast(), c2u.len(), libc::MSG_NOSIGNAL) };
            if n == 0 { return IO_ERROR; }
            if n < 0 {
                let e = std::io::Error::last_os_error();
                if e.kind() != std::io::ErrorKind::WouldBlock && e.kind() != std::io::ErrorKind::Interrupted { return IO_ERROR; }
            } else { c2u.consume(n as usize); *up_total += n as u64; last_data = Instant::now(); }
        }
        if fds[0].revents & libc::POLLOUT != 0 && cw && !u2c.is_empty() {
            let n = unsafe { libc::send(client, u2c.pending().as_ptr().cast(), u2c.len(), libc::MSG_NOSIGNAL) };
            if n == 0 { return IO_ERROR; }
            if n < 0 {
                let e = std::io::Error::last_os_error();
                if e.kind() != std::io::ErrorKind::WouldBlock && e.kind() != std::io::ErrorKind::Interrupted { return IO_ERROR; }
            } else { u2c.consume(n as usize); *down_total += n as u64; last_data = Instant::now(); }
        }
        if !cr && c2u.is_empty() && uw { unsafe { libc::shutdown(upstream, libc::SHUT_WR); } uw = false; }
        if !ur && u2c.is_empty() && cw { unsafe { libc::shutdown(client, libc::SHUT_WR); } cw = false; }
    }
}

/// Relay two already-authorized TCP sockets. The caller owns both descriptors.
/// Return values: 0 client close, 1 upstream close, 2 idle timeout, 3 policy
/// revoked/control failure, 4 socket/runtime error.
#[no_mangle]
pub unsafe extern "C" fn drlink_relay_bidirectional(
    client_fd: c_int,
    upstream_fd: c_int,
    revalidate_ms: u64,
    idle_ms: u64,
    reauthorize: Option<Reauthorize>,
    context: *mut c_void,
    upstream_bytes: *mut u64,
    downstream_bytes: *mut u64,
) -> c_int {
    if client_fd < 0 || upstream_fd < 0 || reauthorize.is_none() || upstream_bytes.is_null() || downstream_bytes.is_null() { return IO_ERROR; }
    ptr::write(upstream_bytes, 0);
    ptr::write(downstream_bytes, 0);
    let result = catch_unwind(AssertUnwindSafe(|| relay(
        client_fd, upstream_fd, Duration::from_millis(revalidate_ms.max(1)),
        Duration::from_millis(idle_ms.max(1)), reauthorize.unwrap(), context,
        &mut *upstream_bytes, &mut *downstream_bytes,
    )));
    result.unwrap_or(IO_ERROR)
}

#[cfg(test)]
mod tests {
    use super::{Buffer, MAX_BUFFER};

    #[test]
    fn relay_buffer_never_admits_more_than_its_fixed_bound() {
        let mut buffer = Buffer::new();
        let block = vec![7u8; MAX_BUFFER];
        buffer.push(&block);
        assert_eq!(buffer.len(), MAX_BUFFER);
        assert_eq!(buffer.available(), 0);
        buffer.consume(MAX_BUFFER / 2);
        assert_eq!(buffer.available(), MAX_BUFFER / 2);
        buffer.push(&block[..MAX_BUFFER / 2]);
        assert_eq!(buffer.len(), MAX_BUFFER);
        assert_eq!(buffer.available(), 0);
    }
}

