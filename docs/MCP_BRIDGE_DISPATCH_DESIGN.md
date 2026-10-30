# MCP Bridge dispatch and concurrency — design proposal (AUD-21)

> **Status: proposal, non-normative.** Not implemented and not deployed. It needs
> owner approval before any code change. It does not override `PRODUCT_MASTER.md`,
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
| 2 | D2 and D3 | Pickup delay and idle load |
| 3 | D4 | Executed-but-failed results |
| 4 | D5 and D6 | Overload behaviour and visibility |

Rollback: revert the step. Agents are upgraded together with the Server for steps 2 and later.

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
