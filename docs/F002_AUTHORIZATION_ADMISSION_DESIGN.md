# F-002 Remote Access authorization throughput and fairness — design review

Status: **DESIGN / REVIEW ONLY — REQUIRES OWNER SIGN-OFF BEFORE ANY IMPLEMENTATION.**
No authorization, cache, or admission code is changed by this document.

Finding: CLI100 F-002 (P-005, P-021). Under an open-loop new-connection load of ~30 CPS
and above against one service, connections were reset, successful CPS plateaued at
~40-50 new conn/s for the Server, and unrelated services on other Agents failed until
~27 s after the load stopped. The failure reason was not visible to the user.

## 1. Current mechanism (source facts)

- Every public TCP connection triggers frps `NewUserConn` → one shared HTTP plugin,
  `server/frp-access-plugin.py` (`AccessServer`, `lib/frp_bounded_server.py`).
- Admission: `max_concurrent = 32` workers (`FRP_ACCESS_MAX_CONCURRENT`), accept
  backlog 32. Above 32 in flight, the accept thread answers immediately with the
  fail-closed `503 {"reject":true,"reject_reason":"server busy"}`. frps treats this as
  a reject, so the user sees a reset. The budget is **Server-wide, not per service**.
- `/healthz` shares the same 32-slot budget (see F-027: diagnostics now names this
  saturation explicitly instead of a generic health failure).
- Per decision (`PolicyCache.open_isolated` + `RP.authorize_remote`): a fresh
  request-private read-only SQLite connection (bounded by an 8-reader semaphore),
  integrity/schema validation, `generation_status` → `plane.status()` scan,
  `build_proxy_map` (whole map over every client and every published service, about
  2 proxy-name computations per service, fail-closed on collision), then policy
  evaluation. All of this is Python CPU under one GIL, so decisions are effectively
  serialized.
- The request-private connection design exists for FD bounds. Under the unix VFS,
  overlapping short-lived readers beside a long-lived connection to the same file
  retain descriptors until every lock is released (see the `PolicyCache` docstring).

## 2. Measurements (bounded, isolated; not lab or production numbers)

In-process decision benchmark (no sockets; `/tmp/claude-f002/bench.py`, 3 hosts, allow rule):

| services | ms / decision | serial ceiling |
|---|---|---|
| 20 | 7.83 | ~128 CPS |
| 200 | 15.63 | ~64 CPS |

Profile at 200 services: `build_proxy_map` ~50%, `status()`/integrity ~20%,
connection open ~18%, evaluation ~15%. Folding the N+1 `remote_service_meta` lookup
into a JOIN reduced SQL statements 250→50 per decision but did **not** reduce latency
(15.79/14.83 ms), so it was reverted.

Live loopback fixture (pinned frp 0.71.0 frps/frpc, real plugin handler and
`AccessServer`, disposable control DB with no Remote policy, frpc TLS on, closed-loop
64 B echo, 6 s per cell, `/tmp/claude-f008/fixture.py`). Successful CPS:

| plugin | poolCount | conc 1 | conc 8 | conc 32 |
|---|---|---|---|---|
| none | 0 / 1 / 5 | 421 / 415 / 416 | 961 / 1012 / 951 | 1226 / 1197 / 1160 |
| real, 20 services | 0 / 1 / 5 | 70 / 67 / 59 | 29 / 29 / 29 | 30 / 35 / 31 (329-475 resets) |
| real, 200 services | 0 / 1 / 5 | 38 / 34 / 34 | 7 / 7 / 7 | 12 / 11 / 12 (346-382 resets) |

- `poolCount` 0/1/5 makes no material difference at loopback, with or without the plugin.
- With the plugin, **CPS drops as concurrency rises** (70 → 29 at 20 services; 38 → 7 at 200).
  A probe on an unrelated proxy shows the same latency inflation (~1-5 s at conc 32): one
  shared authorizer.

**Root cause of the drop (measured in-process, no sockets):** decision threads contend
with each other inside one Python process (GIL plus SQLite's process-global mutexes
across hundreds of short statements per decision; system CPU time ≈ user time).

| 20 services | decisions/s |
|---|---|
| 1 thread | ~118-137 |
| 8 threads (current 8 DB-reader slots) | ~32 |
| 8 threads, decisions serialized by one lock | ~107 |
| 8 separate processes | ~873 |

Throughput at 32 HTTP worker threads vs DB-reader slot count (`ACCESS_DB_MAX_CONCURRENT`;
each slot is held from open to `plane.close()`):

| services | 1 slot | 2 slots | 4 slots | 8 slots (current) |
|---|---|---|---|---|
| 20 | 104 | 104 | 69 | 36 |
| 200 | 54 | 39 | 15 | 7.5 |

Changing the GIL switch interval does not change the drop. Removing the per-decision
`PRAGMA integrity_check` (measurement only) raises serial throughput (20 services:
95 → 174/s) but not the 8-thread drop. Note that `authorize_remote` calls
`generation_status(plane, "remote")` without `validated_revision`, so every decision
runs a full `integrity_check` and `foreign_key_check` (cost grows with total DB size,
including revision history).

## 3. Problem decomposition

1. **Per-decision CPU grows with total Server size** (O(clients + services) per
   connection) instead of O(1) for the proxy being authorized.
2. **One shared admission budget**: a single hot service can occupy all 32 slots,
   and every other service is then rejected fail-closed (cross-tenant blast radius).
3. **Opaque failure**: the busy reject reason is visible only in the plugin's HTTP
   response; users see resets.
4. **Concurrency drop**: 8 parallel in-process decisions deliver 3-7× *fewer*
   decisions/s than one at a time (section 2). This, not raw per-decision CPU, explains
   the observed ~18-29 CPS plateau.

Any fix must preserve:
- fail-closed on DB unavailability, schema or integrity failure, generation mismatch,
  proxy-name collision, and unknown proxy;
- revocation latency: a rule or host revoke must stop new connections no later than
  it does today (the next decision after commit);
- FD bounds.

## 4. Options

### A. Validated snapshot cache (proxy map + compiled policy), keyed by a coherent fingerprint

Cache the validated `build_proxy_map` result and the compiled policy evaluation inputs
behind an immutable snapshot object, and rebuild it when the fingerprint changes.
P-013 already uses this pattern for Internet Access (`generation_status(validated_revision=...)`,
`cached_generation_status`).

**Invalidation (the security-critical part):**
- `revision` alone is NOT sufficient. About 89 direct SQL mutation sites write
  `clients`, `published_services`, `remote_service_meta`, `port_reservations`,
  `policy_rules` and objects. Some run inside `_mutate` (revision bump); others do
  not. Examples: restore's fail-closed `UPDATE clients/remote_service_meta`, status
  reports, heartbeat projections. `build_proxy_map` reads `clients.hostname/label`,
  which can change without a policy revision.
- `PRAGMA data_version` changes whenever **another connection** commits to the DB.
  It is **per-connection**: it does not change for the connection's own commits
  (the plugin never writes), and it is meaningless on a fresh connection, because
  every new connection starts at its own baseline. A data_version fingerprint
  therefore requires one **long-lived read-only connection** owned by the cache.
- Required fingerprint = (revision, active runtime generation and status, main DB
  inode/size/mtime_ns, data_version from the long-lived connection, config path).
  `ControlPlaneCache._coherent_fingerprint` already computes exactly this tuple.
- Generation (snapshot epoch): monotonically increasing integer per rebuild. A
  decision records the epoch it used (audit), and a decision never mixes two epochs.

**Long-lived-reader FD constraint:** the long-lived connection must not hold an open
read transaction between checks (each fingerprint read is its own short implicit
transaction). Per-request readers must not be opened beside it, or the deferred-close
FD retention reappears. With a cache, request-private readers are no longer needed
for a cache hit; on a miss, the rebuild runs on the long-lived connection under a
single rebuild lock. Net FD use is then **constant (db + wal + shm of one connection)**,
lower than today's up-to-8 readers.

**Race safety:**
- Fingerprint read and snapshot build must observe one consistent DB state. Read
  the fingerprint, build inside one read transaction, re-read the fingerprint, and
  publish only if unchanged (otherwise retry, bounded, then fail closed).
- Publication is an atomic reference swap of an immutable snapshot. Readers never
  observe a half-built map.
- Check before every decision: one `PRAGMA data_version` + `stat()` + revision read
  (~3 cheap statements). A change forces rebuild before deciding. **No time-based
  TTL may allow a decision on a stale snapshot.**

**Positive vs negative caching:** cache only the *inputs* (proxy map, compiled
rules), never per-(proxy, source) *decisions*. Decision results are cheap to
evaluate from compiled inputs. Caching ALLOW decisions risks revocation latency, and
caching DENY decisions risks unbounded cardinality from attacker-controlled source
IPs. Unknown proxy names remain an immediate DENY without insertion.

**Memory/cardinality:** one snapshot of O(clients + services) entries (≈ a few hundred
bytes per service; 10k services ≈ low MB). No per-source state. Bounded by Server size.

**Expected effect:** removes ~70% of per-decision CPU at 200 services (map + status +
open) on a hit; misses happen only after commits.

### B. Fair admission queue (per-service slot budget)

Keep decisions as today, but replace the single 32-slot gate with per-service
(or per-Managed-Host) fairness. For example: a global 32-slot cap plus a per-proxy
cap (e.g. ≤ 8 in flight per proxy) and a short bounded wait queue (e.g. ≤ 50 ms)
before the busy reject.

- Directly addresses blast radius (problem 2) without touching authorization
  semantics. Fail-closed is unchanged (queue full or timeout → same busy reject).
- The proxy name is only known after reading the HTTP body. The accept-time gate
  therefore stays global, and the per-proxy gate is applied in the worker after
  parsing. That needs a small per-proxy counter map: bounded by known proxies, and
  unknown names are rejected before counting.
- Does not raise total throughput. The hot service is capped earlier, so other
  services keep headroom.

### C. Precomputed proxy map maintained on write

Maintain a `proxy_map` table (or a compiled artifact inside the runtime generation)
written in the same transaction as every mutation that affects proxy identity, so
that a decision reads one row by proxy name.

- Best steady-state cost (O(1) indexed read) and no in-memory staleness.
- Highest risk: every one of the ~89 direct mutation sites must keep the table
  consistent, or the map silently diverges. A missed path produces a wrong ALLOW or
  DENY. Needs a consistency checker (doctor + generation compile) and a migration.

### D. Serialize decisions (minimal; no decision-semantics change)

Set the DB-reader bound `ACCESS_DB_MAX_CONCURRENT` from 8 to 1, so one decision runs at
a time while the 32 HTTP workers wait on the existing blocking semaphore.

- Measured 3× (20 services) and 7× (200 services) more decisions/s at 32 workers. Same
  decision code, same fail-closed paths, and fewer FDs (one reader instead of up to 8).
- Risk: the semaphore acquire has **no timeout**. A slow decision delays queued workers
  up to frps's plugin HTTP timeout instead of an explicit busy reject. Pair it with a
  bounded acquire (e.g. ≤ 1 s → the existing `server busy` reject), which is a small
  admission change in the same hot path.
- A multi-process worker model (8 processes ≈ 873/s at 20 services) scales further, but
  it is a larger service/IPC change.

### E. Validated-revision generation check (P-013 pattern)

Call `generation_status(..., validated_revision=...)` on the request connection
after the cache validated the fingerprint, instead of a full `integrity_check` and
`foreign_key_check` per decision. This is measured to nearly double serial throughput.
It depends on A's fingerprint correctness: the integrity scan then runs only on
fingerprint change.

### Comparison

| | Throughput | Blast radius | Semantic risk | FD | Effort |
|---|---|---|---|---|---|
| A cache | high gain on hits | unchanged | medium (invalidation) | lower | medium |
| B fair queue | none | **fixed** | low | same | low-medium |
| C precomputed map | highest | unchanged | high (write paths) | same | high |
| D serialize (1 slot + bounded wait) | **3-7× measured** | improved (no collapse) | low | lower | low |
| E validated revision | ~1.2-1.8× serial | unchanged | medium (needs A) | same | low after A |

**Recommendation (for owner decision):** D first (smallest change, largest measured
gain, removes the concurrency drop that matches the observed ~18-29 CPS lab plateau).
Then B for per-service fairness, then A+E for throughput, with the invariants above.
C is not recommended until the mutation paths are consolidated behind `_mutate`.

## 5. Tests required before merge (any option)

- Revocation: commit a rule disable or host revoke from another connection; the very
  next decision must DENY (A: data_version path; also revision-only and
  hostname-only changes). Restore's direct `UPDATE`s must invalidate.
- Fail-closed matrix unchanged: DB missing or locked, integrity failure, generation
  mismatch, proxy collision, unknown proxy, malformed request.
- Race: a writer thread mutates continuously while N readers decide. No decision may
  use a snapshot older than a commit that completed before the decision started.
- FD bound: sustained decisions with concurrent writers; DB descriptor count stays
  constant (extend the existing 16-slot FD test in `tests/test-access-control.py`).
- Fairness (B): with one proxy saturating, a second proxy's decisions succeed within
  bound and are never answered "server busy" while the global budget has room.
- Benchmarks at 20/200/2000 services in the isolated fixture (no lab saturation).

## 6. Canary and rollback

- Feature flag in Server config (default off) for each of A and B, read at plugin start.
- Canary: enable on the disposable lab Server, run the bounded loopback fixture, then
  the CLI100 P-005/P-021 scenarios with explicit owner approval for load.
- Rollback: flip the flag off and restart `drlink-access`. No schema change for A or B,
  so rollback has no data migration. C would need a migration and down-migration.

## 7. Open decisions (owner)

1. Approve option D (reader bound 1 + bounded acquire timeout value), B and/or A+E
   (per-proxy cap and queue-wait values).
2. Whether the busy reason should be surfaced to users (e.g. Server-side
   `show status` counter of busy rejects in the last N minutes).
3. Numeric CPS SLO (overlaps F-030: no approved throughput SLO exists).
