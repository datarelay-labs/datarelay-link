# MCP Bridge dispatch and concurrency — design proposal (AUD-21)

> **Status: proposal, non-normative.** Not implemented and not deployed. It needs
> owner approval before any code change. It does not override `PRODUCT_MASTER.md`,
> `SECURITY.md` or `AI_ACCESS_MCP.md`.
> Tracking: Issue #230 (AUD-21). Cause logging already proposed in PR #240.

## 1. Problem

Two measured defects on the MCP Bridge to Agent path. Base: main `02a1e498`;
isolated harness (real ControlPlane, HTTP server and AgentLoop on loopback).

| Defect | Evidence |
|---|---|
| Concurrency | 12 threads x 4 rounds of `exec`: 6 and 10 of 48 calls returned `-32603 internal error`. Logged causes: 9x `sqlite3.InterfaceError` (SQLITE_MISUSE) in read paths (`get_ai_job`, `get_principal`, `get_object`, `_matched_ai_rule_rows`, `_ref_name_match`); 1x `TypeError` in `current_revision` called from `record_ai_activity` |
| Dispatch latency | Sequential `exec`: p50 62 ms, p95 2,029 ms. With the Agent idle, all six calls took 1.62-1.68 s (median 1,675 ms) |

Bridge-side cost is not the bottleneck (p50): authorization 0.53 ms, audit write
0.73 ms with `synchronous=FULL` (0.30 ms with `NORMAL`), one result poll 0.02 ms,
`list_hosts` 2.35 ms. Per-call server cost is about 2 ms.

## 2. Current behaviour

- One `sqlite3.Connection` (`check_same_thread=False`) is shared by every request
  thread. Request threads are not bounded. `ControlPlane._db_lock` guards only
  three OAuth paths.
- The Bridge waits for a result by reading `get_ai_job` every 0.05 s per in-flight
  call (`_dispatch_endpoint`).
- The Agent claim loop waits 0.05 s after it found a job, otherwise
  `AI_AGENT_IDLE_POLL_SECONDS` = 2.0 s. `/agent/v1/claim` returns immediately.
- Each claim refreshes liveness (row rewrite throttled to 30 s;
  `MANAGED_HOST_LIVENESS_SECONDS` = 120), sweeps expired queued and stale running
  jobs, selects, and commits.
- `record_ai_activity` runs after `_dispatch_endpoint`. An exception there returns
  `internal error` after the command already ran.

## 3. Goals and non-goals

Goals
- G1: no `-32603` from concurrency; 64 simultaneous valid calls all complete normally.
- G2: a connected, idle Agent picks up a job with p95 <= 100 ms (loopback harness,
  excluding network round trip).
- G3: no weaker security. Authorization is evaluated on every call, audit stays
  durable (`synchronous=FULL`), and a call is rejected when its intent cannot be recorded.
- G4: compatible with deployed Agents; staged rollout with rollback.
- G5: bounded resources and an explicit busy answer under backpressure.

Non-goals: replacing SQLite; changing authorization semantics or caching
decisions; changing how the Agent executes work; lowering the idle poll interval.

## 4. Proposal

### 4.1 Database ownership (G1)
- Request threads use thread-local read connections from a factory (WAL,
  `query_only`). No cursor crosses threads.
- All writes go through one serialized writer with `BEGIN IMMEDIATE`, short
  transactions and one central busy-retry policy. The shared connection is removed.
- Staged: read paths first (all nine observed SQLITE_MISUSE are reads), then writes.
  Compatibility with in-process CLI use (`commit_if_autonomous`) must be verified.

### 4.2 Wake on enqueue (G2)
- An in-process dispatch hub keyed by client id. `enqueue_ai_job` notifies it.
- `/agent/v1/claim` accepts an optional `wait_ms` (at most 25,000). With no job it
  blocks on the hub until a job arrives or the time expires, then runs the existing
  claim. A request without `wait_ms` behaves exactly as today, so deployed Agents
  are unchanged.
- The response advertises `long_poll: true`. A new Agent sends `wait_ms`, re-claims
  immediately, and falls back to the 2.0 s idle poll when the Server does not advertise it.
- 25 s is inside the 120 s liveness window; the 30 s refresh throttle is unchanged.

### 4.3 Event-based result wait
- `/agent/v1/complete` signals a per-job event and `_dispatch_endpoint` waits on it.
  The database stays the source of truth: on timeout or a missed signal the Bridge
  falls back to a read at 1 s intervals, which covers restarts and multiple
  processes. Waiting threads no longer touch the database every 0.05 s.

### 4.4 Execution and audit ordering
- Write an intent row (`dispatching`, correlation id) before enqueue; fail closed
  when it cannot be written.
- Complete the row after the result. A failed completion write must not replace
  the execution result: return the result with `audit_status: failed` and log at ERROR.
- Any error after enqueue carries `job_id` and `retryable: false`, so the caller
  reads job state instead of retrying.

### 4.5 Backpressure
- Bounded worker pool and accept queue. Over the limit, before dispatch, answer an
  explicit busy error with `retryable: true`.

### 4.6 Observability
- Record `queue_ms`, `run_ms` and `total_ms` per job; keep the correlation id from PR #240.

## 5. Rollout

Each step ships on its own, RED to GREEN, with no deployment while Issue #165 is in progress.

| Step | Change | Switch |
|---|---|---|
| A | Thread-local read connections | none |
| B | Single writer | none |
| C | Hub, long-poll claim, event result wait | `DRLINK_MCP_LONG_POLL`, default off, on after E2E |
| D | Intent-first audit | none |
| E | Worker pool and backpressure | limit setting |

Version skew: Server first. Old Agents keep the 2.0 s poll; new Agents long-poll
only when the Server advertises it. Rollback: switch C off; revert A, B, D or E.

## 6. Verification

- `tests/test-mcp-bridge-concurrent-calls.py` (PR #240): RED today, GREEN after A+B,
  then a 64-way variant.
- `tests/test-mcp-agent-dispatch-latency.py` (this change): RED today (median
  1,675 ms), GREEN after C (median <= 250 ms; p95 <= 100 ms in the perf harness).
- New tests: an Agent without `wait_ms` still receives jobs; a lost notification
  falls back to a database read; an audit write failure after execution returns the
  result with `audit_status: failed`; an intent write failure rejects without
  enqueue; busy is returned at the queue limit.
- The 12 existing MCP and OAuth test files and the derived-artifact closure check stay GREEN.
- Each RED test is registered in `run-fast-pr.sh` and `run-all.sh` when its fix lands.

## 7. Rejected alternatives

| Alternative | Why not |
|---|---|
| Raise `busy_timeout`, retry in the client | The error is API misuse, not a busy database; a retry can run a mutating command twice |
| One global lock around the database | Serializes every request and hides the ownership problem instead of fixing it |
| Lower the idle poll to about 0.2 s | About 10x more claim requests per Agent, each with sweeps and a commit; still a poll |
| Relax `synchronous` | Saves about 0.4 ms per call and weakens audit durability |
| Cache authorization decisions | Saves about 0.5 ms per call and breaks per-call re-evaluation |

## 8. Open questions for the owner

1. Approve an optional `wait_ms` on `/agent/v1/claim` (backward-compatible protocol addition)?
2. Keep the order A, B, C, D, E, or merge A and B?
3. Is a worker cap of 32 acceptable as a starting value (to be set after a load test)?
4. Is any deployed Agent unable to upgrade and in need of the 2.0 s behaviour as a supported mode?
