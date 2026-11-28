# R1 bounded Rust egress relay PoC

This is an isolated performance/behavior experiment. It is not linked into the
product runtime, installer, release artifacts, or public interface. The Python
reference calls `lib/frp_egress_runtime.py::relay_bidirectional`; the Rust
candidate is a Tokio TCP relay. A small Python service remains the shared
policy and audit authority for both candidates. The origin is a loopback echo
server. This keeps the comparison on real sockets while excluding product
policy duplication from the native code.

## Build and run

The recorded run used the existing Rust 1.75 toolchain, a locked Tokio 1.35.1
dependency graph, and CPython 3.12.3. On that host:

```bash
LD_LIBRARY_PATH=/home/aella/.local/rust-1.75/usr/lib/x86_64-linux-gnu:/home/aella/.local/rust-1.75/usr/lib \
PATH=/home/aella/.local/rust-1.75/usr/bin:$PATH \
CARGO_HOME=/home/aella/drlink-validation/codex-lperf-rust-20261126/rust-cargo-home \
cargo build --release --locked --manifest-path experiments/r1-rust-egress-poc/Cargo.toml

python3 experiments/r1-rust-egress-poc/run.py \
  --concurrency 10,50,100 --rounds 3 --payload-kib 256 \
  --order python,rust \
  --output /tmp/r1-python-rust-order-pr.json

python3 experiments/r1-rust-egress-poc/run.py \
  --concurrency 10,50,100 --rounds 3 --payload-kib 256 \
  --order rust,python \
  --output /tmp/r1-python-rust-order-rp.json
```

Each run also checks four simultaneous 4-MiB streams through a slow echo peer,
policy denial and live-session revocation, client half-close, idle timeout,
audit acknowledgment failure, and 40 allowed transfers with a concurrent
denial. It verifies all returned bytes and exact event counts. Buffers are
limited to 256 KiB per direction, admission to 256 sessions, and listener
backlog to 64.

Raw source-hashed results from the owner-directed run are committed in
`evidence/`. Reports record Python/Rust source hashes, Rust binary hash, tool
versions, host, candidate ordering and process CPU/RSS measurements.

## Limits

The fixture uses one Boolean policy fixture and a loopback destination. It does
not implement or validate the product's canonical SQLite rules, FQDN
resolution, unsafe-address/SSRF checks, DNS rebinding defenses, HTTP Forward,
HTTPS CONNECT ClientHello/SNI rules, ECH, external network, FRP listener
activation, installed-service packaging, or real Managed Host behavior. The
result supports a bounded transport investigation; it does not establish
product adoption or release qualification. Keep Python authorization, policy,
DNS and audit as the sole authorities. The existing Python relay remains the
rollback implementation.
