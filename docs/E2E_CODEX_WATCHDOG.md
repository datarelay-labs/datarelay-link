# CLI-only E2E Codex watchdog

Purpose: keep **one existing, owner-selected** Codex E2E session progressing. This is
a local operator supervisor, not a product service. It never runs a test itself,
never grants approval, never changes test outcome fields, never selects another HEAD,
and never creates a second actor while Codex is alive.

## Current lane

- tmux target: codex:0.0, user: aella
- Ledger: /home/aella/drlink-validation/codex-e2e-supervised-20261105/SCENARIO_TRACKER.tsv
- UI states: Pursuing goal (observe), Goal stalled (bounded auto-resume),
  Goal paused (no action), approval request (no action)
- Source of truth: 116 unique scenario IDs and WORK_STATE. Historic
  SNAPSHOT_RESULT is never used as current status.
- Scenarios in PARTIAL are the pending queue in canonical ledger order.
  PASS, SCOPED PASS, FAIL, measured-only and AI/MCP exclusions are terminal
  for scheduling. Remaining environment-blocked assertions are reported but never
  silently promoted to PASS.
- After a stall, the watcher clears a stale multiline draft with Ctrl-C,
  verifies the blank composer, submits only the standalone /goal resume command
  to the same tmux pane, and verifies the UI actually changes to Pursuing goal.
  This fixes the observed bug where a long prompt plus the slash command
  remained unsubmitted in the editor. The watcher never presses Tab during
  this transition. Another stall rotates the retry-accounting target among
  eligible PARTIAL scenarios after a 15-minute cooldown, with at most two tries
  per scenario; the resumed Codex Goal independently selects the actual test
  work. A resume without a verified UI transition is recorded as failure.
- If the Codex process exits while PARTIAL assertions remain, the watcher
  resumes ONLY the pinned exact Codex session ID from codex_session_id.txt
  when the original tmux pane is a verified idle shell. It validates the
  existing local rollout file, launches resume once, and chooses the known
  Resume paused goal menu only if that exact menu appears. It then verifies
  the Pursuing goal UI; any other approval or unexpected UI fails closed.
  No new session, separate actor, or candidate is created.
- Recovery is checked every 60 seconds with a 90-second minimum between
  process relaunch attempts and a circuit breaker of 3 relaunches/hour and
  12/day. Repeated failure is reported, not treated as PASS. This limits
  runaway model consumption when missing resources or genuine blockers
  prevent meaningful test progress. The test outcome ledger is preserved.
- Pending human approval, deliberate pause, unknown UI, malformed ledger,
  missing tmux session, or unavailable process evidence are fail-closed.
- Every invocation has a short timeout. No infinite REPL and no unsafe automatic
  process kill, environment reset, sudo, SSH, credential change or bypass.

## Installation

Pin the latest verified resumable session UUID as aella in the E2E run
directory in codex_session_id.txt. Do not overwrite the older thread.id.
For the November 9 run it is:

    01a1b689-b0b8-7680-a91f-02d3e744cd42

Then install as aella on dev-drlink:

    bash tools/install_e2e_codex_watchdog.sh

The installer repairs the existing drlink-codex-e2e.service user unit
(previously pointing at a missing supervisor.sh, restart status 127).
It installs the Python file and wrapper in the E2E run directory, replacing
only the broken supervisor, not the active Codex session.

## Verify

    systemctl --user is-active drlink-codex-e2e.service
    systemctl --user status drlink-codex-e2e.service --no-pager
    python3 /home/aella/drlink-validation/codex-e2e-supervised-20261105/e2e_codex_watchdog.py status
    cat /home/aella/drlink-validation/codex-e2e-supervised-20261105/e2e_watchdog_status.json

The watcher writes e2e_watchdog_status.json, e2e_watchdog_state.json, and
e2e_watchdog_events.jsonl to the run directory. It does not overwrite the
scenario ledger, test reports, or existing E2E evidence.

## Disable / roll back

    systemctl --user disable --now drlink-codex-e2e.service

This never stops the live Codex actor. To change the retry limit, edit the
wrapper's --max-attempts and restart only the watchdog service. To reconsider
scenarios whose retry budget was exhausted, review their evidence and explicitly
reset only e2e_watchdog_state.json after correcting the underlying dependency.
Do not reset the scenario ledger.

This mechanism cannot force a genuine security/platform denial to succeed or
make a failing product scenario PASS; it preserves and surfaces those unresolved
outcomes for the final report.
