# Data Relay Link bounded MCP runtime

This Rust component owns bounded runtime operations around existing Python
authority: atomic, nonblocking dispatch admission; retention and paging for
streamed job output; stdout/stderr draining for Python-spawned children; one
ready-connection accept from Python's already bound HTTP listener; and bounded
request-body reads and response-body writes through Python's existing HTTP/TLS
handler. The
output window retains the newest 1 MiB and returns pages up to 64 KiB, matching
the Python cursor contract. Python continues to authenticate requests,
evaluate AI Access, own durable jobs and audit, dispatch to Agents, choose
timeouts, terminate process groups, reap children, frame HTTP responses, and
own the socket/TLS connection. A blocked Python writer backpressures the
handler; failed or stalled writes fail closed.

Rust accept uses close-on-exec descriptors and returns the accepted descriptor
to Python, which constructs the socket, obtains the peer address, frames HTTP,
and owns connection/TLS handling. Python mode keeps the standard socket accept
path. In `auto`, a library without the accept symbol keeps Python accept; an
explicit Rust selection fails closed if the symbol is unavailable.

On Linux, child exit is observed with non-reaping `waitid(WNOWAIT)`; on macOS,
the helper uses a persistent `kqueue` `EVFILT_PROC/NOTE_EXIT` watcher across
timeout/retry drain calls. Python owns and closes that watcher after final EOF
or error. Both paths leave the child waitable so Python retains reaping and
process-group cleanup authority. The 2026-11-27 Apple Silicon retest found that
the one-shot exit event could be missed on retry and that the completed-child
path unnecessarily signaled its process group and received `EPERM`. The
versioned stateful drain ABI now carries the observed leader-exit flag in the
Python-owned process object across calls, and group signaling is limited to
incomplete drains. Drain status `9` identifies an exited leader whose
descendants still hold a captured pipe; Python terminates the process group and
performs a final EOF drain. The Apple Silicon workflow passed the stateful
process lifecycle regression on exact candidate `08b62d9` (run
`45958802619`). Denials on required cleanup paths remain hard
errors. On macOS, `auto` skips an older
library without the stateful ABI and uses Python; explicit Rust selection fails
closed.

The Python owner always releases the native process watcher when a capture
ends, including a final EOF timeout when no stdin writer was created. A final
drain failure is not reported as complete output: Agent capture raises after
closing streams and reaping the child, and Server full-control returns
`output_complete: false` with a bounded lifecycle error in the completed job
receipt. The job, account, timeout, termination, and reap authority stays in
Python.

The library is selected with `DRLINK_MCP_RUNTIME=rust` and
`DRLINK_MCP_NATIVE_LIBRARY=/path/to/libdrlink_mcp_runtime.so`. `auto` loads an
available packaged library and otherwise uses the existing Python dispatch and
process/pipe lifecycle paths;
`python` selects the rollback implementation. Explicit Rust selection fails
service initialization if the library cannot be loaded. The Linux x86_64
Agent and Server bundles include both Rust shared libraries under the
target-specific native directory and record the Rust version, source HEAD,
Cargo.lock hashes, and library hashes in `runtime-build.json`. The Agent
runtime lineage manifest covers these files; the Server project-file manifest
includes them in install, update, and rollback. Linux ARM64 and macOS native
library package assets remain to be qualified and added.
R2 currently covers dispatch admission, one ready-listener accept, bounded
streamed-result retention, bounded request-body reads and bounded outbound
response writes, and the per-subscription condition wait used for bounded job
result wakeups. Python's DB watcher sends the signal and Python re-reads SQLite,
checks job ownership/status and consumes the durable result. HTTP/TLS stream
ownership, JSON parsing, authorization and connection lifecycle remain in Python.
R3 process-pipe
integration is present for Linux/macOS Agent and Server paths; Linux regression
passes. Apple Silicon testing exposed retry watcher state loss and unnecessary
group signaling after successful EOF; the stateful ABI and cleanup scope are
corrected and await exact-head retest. Required process-group cleanup denials
remain failures.

Build and unit test with the pinned Rust 1.75 toolchain:

```sh
cargo test --locked --manifest-path native/drlink-mcp-runtime/Cargo.toml
cargo build --release --locked --manifest-path native/drlink-mcp-runtime/Cargo.toml
scripts/build-native-runtime-assets.sh
```
