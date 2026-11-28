# Data Relay Link native egress runtime

This Rust library owns only bounded bidirectional socket I/O after Python has
authorized and connected the client and upstream sockets. Python remains the
sole authority for policy, DNS/SSRF validation, reauthorization and audit.
The library exposes a narrow C ABI with an explicit Python reauthorization
callback and fixed per-direction buffer bounds.

The library is not yet included in an installer or release bundle. Product
runtime selection is therefore automatic Python fallback unless an explicitly
configured library is present. Packaging, supported architecture qualification,
independent security review and real network E2E remain required before the
native runtime can be enabled by default.

Build with the repository's pinned Rust 1.75 toolchain:

```sh
cargo build --release --locked --manifest-path native/drlink-egress/Cargo.toml
```

The resulting library name is `libdrlink_egress.so` on Linux. The locked `libc`
dependency is pinned exactly; the crate source is retained at
`native/drlink-egress/src/lib.rs` for reproducible builds and provenance.
