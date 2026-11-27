# Data Relay Link bounded MCP runtime

This Rust component currently owns one narrow MCP runtime operation: atomic,
nonblocking admission against the existing per-process dispatch budget. Python
continues to authenticate requests, evaluate AI Access, write durable jobs and
audit, dispatch to Agents, wait for results, and serialize/send MCP responses.

The library is selected with `DRLINK_MCP_RUNTIME=rust` and
`DRLINK_MCP_NATIVE_LIBRARY=/path/to/libdrlink_mcp_runtime.so`. `auto` loads an
available packaged library and otherwise uses the existing Python limiter;
`python` selects the rollback implementation. Explicit Rust selection fails
service initialization if the library cannot be loaded. The library is not yet
included in installer bundles. MCP connection I/O, result-wait, streaming and
backpressure work remains open under R2.

Build and unit test with the pinned Rust 1.75 toolchain:

```sh
cargo test --locked --manifest-path native/drlink-mcp-runtime/Cargo.toml
cargo build --release --locked --manifest-path native/drlink-mcp-runtime/Cargo.toml
```
