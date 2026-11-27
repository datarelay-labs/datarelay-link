# Data Relay Link bounded MCP runtime

This Rust component currently owns three narrow runtime operations: atomic,
nonblocking admission against the existing per-process dispatch budget,
bounded retention and paging for streamed job output, and polling/draining
stdout and stderr for child processes that Python already spawned. The output
window retains the newest 1 MiB and returns pages up to 64 KiB, matching the
existing Python cursor contract. Python continues to authenticate requests,
evaluate AI Access, own durable jobs and audit, dispatch to Agents, choose
timeouts, terminate process groups, reap children, and shape/send MCP
responses.

The library is selected with `DRLINK_MCP_RUNTIME=rust` and
`DRLINK_MCP_NATIVE_LIBRARY=/path/to/libdrlink_mcp_runtime.so`. `auto` loads an
available packaged library and otherwise uses the existing Python dispatch and
process/pipe lifecycle paths;
`python` selects the rollback implementation. Explicit Rust selection fails
service initialization if the library cannot be loaded. The Python adapter is
included in Server bundles; native shared-library packaging is still pending.
MCP connection I/O and result-wait work remain open under R2. Linux/macOS
Agent and Server executor integration is in progress under R3.

Build and unit test with the pinned Rust 1.75 toolchain:

```sh
cargo test --locked --manifest-path native/drlink-mcp-runtime/Cargo.toml
cargo build --release --locked --manifest-path native/drlink-mcp-runtime/Cargo.toml
```
