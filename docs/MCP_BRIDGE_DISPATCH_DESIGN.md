# MCP Bridge dispatch and concurrency — design proposal (AUD-21)

> **Status: proposal, non-normative.** Steps 1 and 2 (incl. 2e) are implemented on draft/merged PRs
> (see section 5); steps 3 and 4 are not. Nothing is deployed. Each further step needs
> owner approval. It does not override `PRODUCT_MASTER.md`,
> `SECURITY.md` or `AI_ACCESS_MCP.md`.
> Tracking: Issue #230 (AUD-21). Cause logging is proposed in PR #240.

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

## 7. Rejected alternatives

| Alternative | Why not |
|---|---|
| Raise `busy_timeout`, retry in the client | The error is API misuse, not a busy database; a retry can run a mutating command twice |
| One global lock around the database | Serializes every request and hides the ownership problem |
| Lower the idle poll to about 0.2 s | About 10x more claim requests per Agent; still a poll |
| Relax `synchronous` | Saves about 0.4 ms per call and weakens audit durability |
| Cache authorization decisions | Saves about 0.5 ms per call and breaks per-call re-evaluation |
| Replace SQLite now | Not needed at 100 Agents and 30 calls (section 4) |

## 8. Open questions for the owner

1. Agents and Server are upgraded together from step 2 on; is that acceptable for the deployment window?
2. Starting thread budgets of 128 held claims and 64 calls; adjust after the load test?
3. Agree to revisit the database only above about 500 sustained writes per second?
4. The 30-simultaneous-call p95 (<= 500 ms) is not met after step 2. Allow parallel job execution
   (or larger claim batches) on the Agent, or relax the target for 30 calls to a single host?
5. Measurements after step 2e (section 5a, correction 2f) show the limit is per-call CPU in one
   interpreter, not database writes. May we (a) cache the compiled, revision-keyed lookup
   structures of the AI Access evaluation, keeping the full evaluation on every call against the
   current revision (one-shot consumption and principal state stay per call), (b) run the AI-jobs
   schema check once per database file instead of on every new connection, and (c) if (a) and (b)
   are not enough, serve the Bridge from several processes? (a) touches the authorization path and
   needs a review of what may be cached; (b) and (c) do not change what is authorized.
