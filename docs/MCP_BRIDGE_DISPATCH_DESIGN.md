# MCP Bridge dispatch and concurrency — design proposal (AUD-21)

> **Status: proposal, non-normative.** Steps 1 and 2 (incl. 2e) are implemented on draft/merged PRs
> (see section 5); steps 3 and 4 are not. Nothing is deployed. Each further step needs
> owner approval. It does not override `PRODUCT_MASTER.md`,
> `SECURITY.md` or `AI_ACCESS_MCP.md`.
> Tracking: Issue #230 (AUD-21). Cause logging is proposed in PR #240.
> Section 5b (2026-10-30) corrects parts of 5a, withdraws the authorization-cache candidate and
> proposes several Bridge processes (D7); nothing in it is implemented.

## 1. Target and where main stands

Owner target (2026-10-30): up to **100 managed hosts (Agents)** and about **30
simultaneous AI calls**. Compatibility with older Agents is **not** required;
Server and Agents are upgraded together.

Measured on main `02a1e498` with the target fleet (100 real Agent workers, real
Bridge, loopback, disposable temp root):

| Measure | Today | Goal |
|---|---|---|
| Claim requests from 100 idle Agents | 46.7 per second (23% of one core) | <= 10 per second |
| Pickup of a new job by an idle Agent | median 1,675 ms | p95 <= 100 ms |
| 30 simultaneous `exec`, 3 rounds (90 calls) | 34 and 50 failed in two runs (`-32603`, connection reset); successful p50 2.1 s | 0 failed; p95 <= 500 ms |

The server-side cost of one call is not the problem (p50): authorization 0.53 ms,
audit write 0.73 ms, one result poll 0.02 ms, about 2 ms in total.

## 2. Causes

1. **One shared SQLite connection.** Every request thread uses the same
   `sqlite3.Connection` (`check_same_thread=False`); `ControlPlane._db_lock` covers
   only three OAuth paths. Logged results: 9x `sqlite3.InterfaceError` (SQLITE_MISUSE)
   in read paths and 1x `TypeError` from an interleaved cursor.
2. **Polling Agents.** The Agent claims every `AI_AGENT_IDLE_POLL_SECONDS` (2.0 s) and the
   claim answers immediately. This gives the 1.7 s pickup delay and a constant request
   stream that grows with the number of Agents. In production the claim goes to the
   **management API** (`/v1/ai-jobs/claim`, served by the allocator process); the Bridge
   `/agent/v1/claim` is the bearer-token path used by tests. The Bridge and the allocator
   are separate processes that share only the SQLite file, so a wake-up cannot rely on an
   in-process event.
3. **Listen backlog of 5.** `ThreadingHTTPServer` does not override
   `request_queue_size`, so Python's default of 5 applies. Likely cause of the
   connection resets under 30 simultaneous connects (to be confirmed after the change).
4. **Result wait by polling.** Each in-flight call reads `get_ai_job` every 0.05 s.
5. **Audit after execution.** `record_ai_activity` runs after `_dispatch_endpoint`, so an
   exception there returns `internal error` after the command already ran.

## 3. Design

- **D1 One connection per request.** Each request borrows its own pooled SQLite
  connection (about 1.7 ms to open, 0.017 ms to reuse), so no connection is ever used
  by two threads. Writers are serialized by SQLite's own write lock (WAL,
  `busy_timeout` 5 s); a separate writer thread is not needed at this write rate
  (section 4). Connections supplied by a caller (doctor, support bundle, in-memory
  preview) are never replaced. **Implemented in step 1 (PR #242, draft):** 90
  simultaneous calls with 100 Agents ran with 0 failures and no busy or locked
  error; scope entry costs about 9 us.
- **D2 Held claim instead of polling.** The claim request takes an optional `wait_ms`
  (at most 25,000). With no job the Server holds the request and answers the moment a job
  is queued for that host. Idle load becomes about 100 / 25 = 4 requests per second and
  pickup takes milliseconds. The 25 s hold fits inside `MANAGED_HOST_LIVENESS_SECONDS`
  (120 s) and the front end's default 60 s read timeout. The production Agent enables it;
  the `AgentLoop` library default stays at 0 so existing callers and tests are unchanged.
  The Agent's request timeout is raised above the hold (it is 8 s today, and a timed-out
  management POST is reported as an ambiguous write).
  **Implemented in step 2 (2b management API, 2c Bridge, 2d Agent).** Empty claims park their
  request slot (`frp_bounded_server.parked_slot`, cap 128) and re-take it before touching the
  database; above the cap the claim answers empty at once and the Agent falls back to its 2 s
  idle poll. The Agent sends `wait_ms=25000` with a request timeout of hold + 10 s; the library
  default stays 0.
- **D2a Cross-process wake-up.** A `DbChangeWatcher` thread per process polls
  `PRAGMA data_version` on its own connection every 10 ms (about 100 trivial local
  checks per second) and wakes waiters when any other connection, in any process,
  committed. The Bridge enqueue therefore wakes a held claim in the allocator, and the
  allocator's completion wakes the Bridge's result wait, with no new IPC surface.
- **D3 Event-based result wait.** The Bridge waits on the watcher instead of reading
  `get_ai_job` every 0.05 s, and rereads the job only after a database change. The
  database stays the source of truth: on timeout or a missed signal the Bridge reads it
  at 1 s intervals. The in-memory handoff for the bearer-token path stays as it is.
- **D4 Intent-first audit.** Write an intent row (`dispatching`, correlation id) before
  enqueue and fail closed if it cannot be written. A failed completion write never
  replaces the execution result: return it with `audit_status: failed` and log at
  ERROR. Any error after enqueue carries `job_id` and `retryable: false`.
- **D5 Listener and worker budgets.** Listen backlog of at least 128 on the Bridge. The
  allocator already bounds requests (`max_concurrent` = 32, slot taken at accept time), so
  100 held claims would use every slot and block `complete` and enrollment. A held claim
  therefore parks its slot while it waits and takes a slot again before touching the
  database; parked claims have their own cap (start: 128) and fall back to an immediate
  empty answer above it. The Bridge keeps a separate call budget (start: 64) with an
  explicit `busy` before dispatch.
- **D6 Metrics.** Record `queue_ms`, `run_ms` and `total_ms` per job; keep the
  correlation id from PR #240.
- **D7 Several Bridge worker processes (proposal; prototype measured in 5b).** K processes serve
  the Bridge on one port and one SQLite file. A worker is today's `MCPBridge`; authorization,
  audit and job state already live in the database and the change watcher (D2a) already works
  across processes, so no new IPC is needed for the call path. Authorization is unchanged: every
  worker evaluates every call against the current database, so a revocation is effective on the
  next call whichever worker receives it. What has to be decided first:
  - *Process-local state.* (1) `FullControlRuntime` keeps the Server-local jobs
    (`server_exec`, `server_run`, `server_git`, `server_job_poll|input|stop`) as OS processes,
    timers and threads of one Bridge process, so a job started on worker A cannot be polled on
    worker B. (2) `_job_results`, `_agents` and `running_ops` are hermetic-test seams and unused
    in production. (3) The in-memory rate limiter (`bridge._rate_hits`: auth failures 30/min,
    token 60/min, register 20/min per source) would allow K times the limit. (4) OAuth code and
    refresh-token redemption must stay one atomic SQLite statement so two workers cannot both
    redeem it; this is to be proven by a test, not assumed.
  - *Server-local full control* (question 6): either workers forward these six tools over a
    0600 Unix socket to one full-control process that holds the runtime (one public URL, workers
    stay stateless, the worker still evaluates AI Access for each call and the full-control
    process re-checks job ownership), or a second listener serves them from one process behind
    a router. The first is recommended.
  - *Listener.* Pre-fork inside the existing service (`server/drlink-mcp-bridge.service` keeps
    one unit and one port; a supervisor restarts a dead worker) with `SO_REUSEPORT`, or one
    systemd template unit per worker. Recommended: pre-fork. K comes from
    `DRLINK_MCP_WORKERS`; K = 1 is today's behaviour and is the rollback. The kernel spreads new
    connections, so a long-lived keep-alive client stays on one worker; acceptable for about
    30 callers, to be watched.
  - *Database.* WAL with `busy_timeout` 5 s stays. Writes from K processes queue on SQLite's own
    write lock; about 120 writes per second (section 4) is a tenth of one writer's capacity.
    The one `database is locked` seen earlier in this work (not analysed) must be run down
    before this ships.
  - *Visibility.* Log the worker number and put it in the intent/audit row (D4, D6).

## 4. Why SQLite and threads are enough at this scale

- A single writer can commit about 1,300 audit-sized writes per second
  (0.73 ms each with `synchronous=FULL`). Thirty calls in flight at about one
  second each is roughly 30 calls per second with about four writes each, so
  around 120 writes per second (estimate), about a tenth of that capacity.
- With held claims, 100 Agents add 100 parked threads and 30 calls add 30 more; this is
  far below what Python threads handle. The management API opens a control-plane
  connection per request (about 6.6 ms with schema checks); at 44-47 idle claims per
  second that is about a third of a core today and about 4 per second with held claims.
- Revisit the database if sustained writes exceed about 500 per second or the fleet
  grows well beyond 100 Agents.

## 5. Rollout

Each step ships on its own, RED to GREEN, with no deployment while Issue #165 is in progress.

| Step | Change | Fixes |
|---|---|---|
| 1 | D1 and the listen backlog (PR #242, draft) | Errors under concurrency |
| 2 | D2 and D3 (implemented, draft PR) | Pickup delay and idle load |
| 3 | D4 | Executed-but-failed results |
| 4 | D5 and D6 | Overload behaviour and visibility |
| 5 | D7 several Bridge worker processes (proposal, needs owner approval) | Latency of 30 simultaneous calls |

Rollback: revert the step. Agents are upgraded together with the Server for steps 2 and later.

## 5a. Step 2 results (measured, loopback, 100 real Agent workers)

| Measure | Before | After step 2 | Goal | Met |
|---|---|---|---|---|
| Pickup of a new job by an idle Agent | median 1,675 ms | 28-55 ms | p95 <= 100 ms | yes |
| Idle claim requests from 100 Agents | 46.7 per second | about 4 per second (100 / 25 s) | <= 10 per second | yes |
| 30 simultaneous calls: failures | 34 and 50 of 90 | 0 | 0 | yes |
| 30 simultaneous calls to one host: p95 | not measurable (failures) | 100-Agent run: median 2.47 s, p95 3.53 s; 2-host harness: median 1.1-1.3 s, p95 1.4-1.7 s | <= 500 ms | **NO** |

The 30-call latency goal is **still not met** and is not claimed as fixed. What was found and
changed since the first measurement (step 2e, targeted wake-ups):

| Measure (30 simultaneous calls, 3 rounds, in-process harness) | Before 2e | After 2e |
|---|---|---|
| Watcher wake-ups in one 11 s burst | 19,311 (215 per call) | not applicable (waiters are signalled by key) |
| CPU per call (whole process) | about 209 ms | not re-measured |
| All 30 to ONE host: median / p95 | 2.68 s / 3.93 s | 0.52 s / 0.75 s |
| 30 calls spread over 30 hosts: median / p95 | 3.27 s / 3.82 s | 1.7-2.4 s / 1.9-2.8 s (3 runs) |

Cause that was confirmed: the change watcher (2a) woke every waiter on every commit, so one
enqueue made about 100 held claims and 30 result waits each run a database look. Now a waiter
subscribes to a key (`claim`/host, `job`/job id); the watcher runs one query per change for all
subscribers and signals only those the change concerns. The 1 s fallback re-read and the
per-call policy re-evaluation are unchanged, and a missed signal still costs latency only.

**Correction (2f, 2026-10-30).** An earlier revision of this section said the remaining time was
mostly `fsync`'d write transactions serialized under `MCPBridge._lock`. That was wrong. Six
experiment variants (fsync removed with `synchronous = NORMAL`, `last_seen` write coalesced, and a
crude prototype without the lock) all stayed at about 1.7 s median for 30 calls spread over 30
hosts, and a single fsync costs about 0.7 ms here. The lock hold times that were reported (about
51 ms per call) are wall-clock times and are inflated by CPU contention; they are not evidence of
slow writes. Group commit and `last_seen` coalescing are therefore **not** recommended on this
data.

What was measured instead (30 calls spread over 30 hosts, 3 rounds = 90 calls, 100 Agent threads,
10-core machine, one run each unless stated):

| Measure | Spread over 30 hosts | All 30 to one host |
|---|---|---|
| Idle 100-Agent fleet, CPU / wall | 0.04-0.07 | 0.07 |
| Process CPU during the burst | 9.9-10.3 s (user 3.8-4.0, sys 6.1-6.3) | 3.0 s (user 1.6, sys 1.4) |
| CPU per call | about 110 ms | about 33 ms |
| CPU in short-lived request threads | about 9.0 of 10.3 s | about 2.2 of 3.0 s |
| Caller moved to a separate process: p95 | 3.25-3.27 s (no better; server CPU 9.7 s) | 2.07 s (one run) |

- The caller threads in the same interpreter are not the cause: moving them to a separate process
  did not reduce server CPU or latency.
- CPU is not bounded by one core (cpu/wall 1.3-1.7), but kernel time is high (43 % of samples in a
  `perf` run): thread wake-ups, context switches and futex calls, which is what many runnable
  threads in one interpreter cost.
- `perf` with Python frames (`python -X perf`), recorded **only while the 90 calls run** (the
  first revision of this correction profiled the whole run including the 100 Agents' start-up
  claims and overstated claim handling; the figures below replace it). One spread-over-30-hosts
  run, 8.9 CPU-s in total: request handling (`do_POST`) 77 %; `call_tool` 48 %; per-call policy
  evaluation (`evaluate_ai_access_v24`) 35 % (3.14 CPU-s, `_ref_name_match` alone 14 %); Agent
  claim handling (`claim_ai_jobs_held`) 18 % (1.63 CPU-s); `ensure_ai_jobs_safety_schema`
  7.2 % (0.64 CPU-s); opening a worker connection (`connect_worker`) 5.3 % (0.47 CPU-s); the
  change watcher 6 %; the harness' own client threads 7-8 %.
- The spread case costs about 3 times the CPU per call of the single-host case because it adds 30
  AI Access rules; the per-call evaluation grows with the number of rules.

Budget: 30 calls through one interpreter in 500 ms leaves about 15 ms of CPU per call. Today a
call costs about 33 ms (one host) to about 110 ms (spread). The 500 ms goal is **still not met**.
Candidate changes, none implemented and each needing owner approval because the evaluation path is
security relevant (section 8, question 5): cache the compiled, revision-keyed lookup structures
used by the evaluation and still evaluate every call against the current revision (one-shot
consumption and principal state stay per call); run the AI-jobs schema check once per database
file instead of on every new connection; and, if that is not enough, serve the Bridge from several
processes. The production topology (separate Bridge, allocator and Agent processes) is still not
measured. `tests/test-mcp-bridge-scale-target.py` stays unregistered in the suites (allowlisted)
and reports this one failure; it also has the 30-hosts case.

Known risk: if an Agent exits while it holds a claim, the Server can claim a job and answer a
dead socket. The job then stays `running` until the stale/fail-closed handling takes it. It is
bounded by that existing handling and is not new in kind, but the window is larger than with 2 s
polling.

**Step 2g (2026-10-30): per-evaluation batching of the AI Access lookups.**
`evaluate_ai_access_v24` ran one database lookup per enabled rule of the identity (about three
per rule). It now reads the destinations of all of the identity's rules together
(`IN (...)`), and memoizes group expansion and permission sets *inside that one evaluation*.
Nothing is kept between calls: every `tools/call` still reads the current rules, identity status
and group membership and evaluates all of them, so the "re-evaluate on each call" property is
unchanged. `tests/test-ai-access-eval-equivalence.py` compares the decision with a verbatim copy
of the previous implementation for 920 identity/destination/permission combinations and asserts
that the number of SQL statements no longer grows with the number of rules (before the change:
29 statements with 12 rules and 69 with 52 rules; the test now requires at most 4 more statements
after 40 more rules are added).

| Measure (30 simultaneous calls, 3 rounds, same harness, 3 runs each) | Before 2g (from 2e) | After 2g |
|---|---|---|
| 30 calls spread over 30 hosts: median | 1.7-2.4 s | 1.42, 1.44, 1.49 s |
| 30 calls spread over 30 hosts: p95 | 1.9-2.8 s | 1.58, 1.72, 1.76 s |
| All 30 to ONE host: median | 0.52 s | 0.48, 0.51, 0.51 s |
| All 30 to ONE host: p95 | 0.75 s | 0.66, 0.73, 0.77 s |

The before and after runs were taken at different times on the same machine, so differences of
about 10 % are within noise; the spread case improved by roughly a quarter, the single-host case
(one rule) did not change, as expected. **The p95 <= 500 ms goal is still not met in either case.**
Remaining per-call CPU is in the many short-lived request threads (thread start, kernel
scheduling) and in `ensure_ai_jobs_safety_schema`/`connect_worker` on each Agent claim; reaching
500 ms for 30 calls through one interpreter needs about 15 ms CPU per call, i.e. a structural
change (several Bridge processes, or fewer per-call thread/connection set-ups) rather than more
micro-optimization.

## 5b. Step 2i-2k results: where the time goes, and several Bridge processes (measured, 2026-10-30)

Setup unless stated: loopback, disposable temp root, 100 real `AgentLoop` workers with held claims,
a shared 10-core machine (other jobs ran at the same time, load average 2.5-9), 30 simultaneous
`exec` calls over 30 hosts, 3 rounds (90 calls). `tests/test-mcp-bridge-scale-target.py` has modes
`SCALE_AGENT_PROCS=N` (Agents in N child processes), `SCALE_SERVER_PROCS=M` (Agent-facing endpoints
in M extra processes), `SCALE_BRIDGE_PROCS=K` (K Bridge worker processes on one `SO_REUSEPORT` port,
prototype only) and `SCALE_CALLS=C` (simultaneous calls); every run prints one `SCALE_METRICS`
line with per-round median/p95, CPU and context switches. The test stays unregistered.

**Corrections to earlier sections**

1. *Harness artifact, fixed in the test.* The first `urllib.request.urlopen` of a process builds the
   default opener and loads the system CA bundle (about 100 ms of CPU). The 30 callers released
   together each built their own, so round 1 looked slow for a reason that has nothing to do with the
   Server: 56 % of the caller process' active samples were in `ssl.load_default_certs`. The test now
   installs one opener before the burst, as a real client keeps its own. Every p95 in 5a and 2g
   includes this artifact (about 0.5-1 s of p95 and about half of the "CPU per call") and is not
   comparable with the figures below.
2. *Authorization is not the cost.* `authorize_ai_capability_v24` takes 1.07 ms per call (one thread,
   warm, 30 rules, 11 SQL statements, the same state as the burst). The perf shares in 5a (2f)
   attribute contention-inflated time to it. The candidate "cache the compiled, revision-keyed lookup
   structures" (question 5a of the previous revision) is **withdrawn**: it could save about 1 ms of a
   call that costs about 33 ms without contention, and it would touch the authorization path.

**Experiments that did not help**

| Experiment (one run each unless stated) | Result |
|---|---|
| Agents moved to 5 child processes, Bridge alone in its process | no better: median 1.37-1.61 s against 1.37-1.49 s |
| `MCPBridge._lock` replaced by a no-op (2 runs) | worse: median +30-60 %, kernel CPU and context switches about 2x |
| At most N threads inside `_authorize` (N = 1, 2, 4) | median -30 to -50 % at N = 1-2, p95 unchanged; the same limit on the Agent-facing paths collapses throughput (stopped after 60 s) |
| Agent-facing endpoints served by one extra process (the production split) | median 1.1-1.3 s, p95 2.0-2.8 s (before the opener fix) |

More runnable threads in one interpreter make everything slower (lock and GIL hand-off, kernel
scheduling): CPU per call rises from about 50 ms with one or two concurrent calls to about 200 ms
with 30, while no single function dominates.

Latency against concurrency, one Bridge process (before the opener fix, Agents in 5 processes): one
call median 33 ms; 2 calls 50 ms; 5 calls 144 ms; 10 calls 330 ms; 15 calls 535 ms; 30 calls 1.5 s
(p95 2.9 s).

**Several Bridge processes.** Prototype in the test only: K worker processes, each a complete
`MCPBridge` with its own `ThreadingHTTPServer`, the same port (`SO_REUSEPORT`) and the same SQLite
file; Agents in 5 other processes; callers in the test process; client opener warmed. Two runs are
listed where two were taken; the second run of K = 4 and K = 8 ran while other jobs pushed the load
average to 6-8.

| Bridge processes | median ms | p95 ms | p95 by round (r1 / r2 / r3) |
|---|---|---|---|
| original harness (Agents and Bridge in one process) | 1,580 | 1,804 | 1,821 / 1,605 / 1,754 |
| Bridge in the test process, Agents separate | 1,375 | 1,535 | 1,539 / 1,478 / 1,434 |
| K = 1 | 1,228 | 1,397 | 1,390 / 1,411 / 1,157 |
| K = 2 | 633 | 837 | 854 / 671 / 683 |
| K = 4 | 350 and 328 | 507 and 701 | 527 / 401 / 380 and 706 / 429 / 394 |
| K = 6 | 277 and 248 | 364 and 360 | 369 / 319 / 375 and 373 / 315 / 280 |
| K = 8 | 212 and 215 | 311 and 416 | 316 / 287 / 278 and 459 / 316 / 235 |

Latency falls almost in proportion to the number of processes. On this machine the 30-call p95 of
500 ms is reached with about **6 worker processes** (4 is borderline, 8 leaves margin), about one
worker per 5 simultaneous calls. No code in the Bridge changed for this measurement.

The worst case, all 30 calls to ONE host (one Agent runs the jobs), measured once each while the
load average was 6-9: Bridge in the test process median 576 ms / p95 809 ms; K = 6 median 255 ms /
p95 411 ms. Question 4 below is therefore answered for 6 workers.

Not measured: the production topology (separate allocator with management-signed claims); a soak;
memory per worker; worker crash and restart; `database is locked` under K workers beyond this burst;
hosts with fewer cores (the table needs about one free core per worker).

## 6. Verification

- `tests/test-mcp-bridge-concurrent-calls.py` (PR #240): 48 simultaneous calls, RED
  today, GREEN after step 1.
- `tests/test-mcp-agent-dispatch-latency.py`: idle pickup, median 1,675 ms today,
  GREEN after step 2.
- `tests/test-mcp-bridge-scale-target.py`: 100 Agents; idle claims <= 10 per second
  and 30 simultaneous calls with 0 failures and p95 <= 500 ms; RED today.
- New tests per step: the watcher wakes on a commit made by another process; a held
  claim on the management API returns as soon as another connection enqueues; a held claim
  does not consume a request slot; a lost completion signal falls back to a database
  read; audit write failure after execution returns the result with `audit_status: failed`;
  intent write failure rejects without enqueue; `busy` at a budget limit.
- The 12 existing MCP and OAuth test files and the derived-artifact closure check stay GREEN.
- Each RED test is registered in `run-fast-pr.sh` and `run-all.sh` when its fix lands.
- D7, written before any code: a revocation made through one worker is refused by the next call
  on every worker; an OAuth authorization code and a refresh token can be redeemed once across
  two workers; a Server-local job started through worker A is polled and stopped through worker B
  with the same ownership checks; the auth-failure limit holds across K workers; a killed worker
  is restarted and in-flight calls to the others are not affected; 8 workers x 100 calls produce no
  `database is locked`; `SCALE_BRIDGE_PROCS=6` p95 stays characterization-only because it depends
  on the machine.

## 7. Rejected alternatives

| Alternative | Why not |
|---|---|
| Raise `busy_timeout`, retry in the client | The error is API misuse, not a busy database; a retry can run a mutating command twice |
| One global lock around the database | Serializes every request and hides the ownership problem |
| Lower the idle poll to about 0.2 s | About 10x more claim requests per Agent; still a poll |
| Relax `synchronous` | Saves about 0.4 ms per call and weakens audit durability |
| Cache authorization decisions | Saves about 0.5 ms per call and breaks per-call re-evaluation |
| Cache the compiled lookup structures of the AI Access evaluation | The evaluation costs about 1 ms per call (5b); nothing to gain and it touches the authorization path |
| Remove `MCPBridge._lock` | Measured worse (5b): the lock is not the bottleneck |
| Limit concurrent threads in the Bridge | Median improves, p95 does not (5b) |
| Replace SQLite now | Not needed at 100 Agents and 30 calls (section 4) |

## 8. Open questions for the owner

1. Agents and Server are upgraded together from step 2 on; is that acceptable for the deployment window?
2. Starting thread budgets of 128 held claims and 64 calls; adjust after the load test?
3. Agree to revisit the database only above about 500 sustained writes per second?
4. The 30-simultaneous-call p95 (<= 500 ms) is not met after step 2. Allow parallel job execution
   (or larger claim batches) on the Agent, or relax the target for 30 calls to a single host?
5. Question 5 of the previous revision (cache the AI Access lookup structures) is withdrawn (5b).
   Section 5b shows that the p95 goal for 30 simultaneous calls needs several Bridge processes
   (about 6 on the 10-core test machine); this also answers question 4 for 6 workers. May we
   write the D7 code (pre-fork workers behind one port, `DRLINK_MCP_WORKERS`, default 1) as a
   draft PR with the tests listed in section 6?
6. Server-local full control (`server_exec`, `server_run`, `server_git`, `server_job_*`) keeps OS
   processes in one Bridge process. Forward these six tools over a 0600 Unix socket to one
   full-control process (recommended), or serve them from a separate listener?
7. The in-memory rate limiter would allow K times the limit with K workers. Move it into SQLite,
   or divide the limits by K?
8. How many cores does the production Server have? The 500 ms goal needs about one free core per
   5 simultaneous calls. Keep the goal, or state it as "p95 <= 500 ms with 6 workers on an
   8-core Server"?
