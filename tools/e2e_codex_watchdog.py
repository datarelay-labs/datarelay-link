#!/usr/bin/env python3
"""Evidence-preserving, fail-closed watchdog for one existing DRLink Codex E2E lane.

Does not execute scenarios, change scenario status, grant approvals, or mutate hosts.
"""
import argparse
import csv
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

DEFAULT_RUN = Path("/home/aella/drlink-validation/codex-e2e-supervised-20261105")
TERMINAL = {
    "HISTORICAL_PASS_DO_NOT_REPEAT_WITHOUT_CAUSE", "SCENARIO_PASS_VERIFIED",
    "CURRENT_CANDIDATE_PASS_AUTHORIZED_DISPOSABLE_SCOPE",
    "SCENARIO_FAIL_REPRODUCED", "EXCLUDED_AI_MCP", "MEASURED_NOT_QUALIFIED",
}
PARTIAL = {"PARTIAL", "SCENARIO_PARTIAL_RECORDED"}
BLOCKED = {"SCENARIO_BLOCKED_VERIFIED"}
APPROVAL = re.compile(
    r"Reviewing approval request|approval required|waiting for approval|"
    r"permission denied by (?:platform|policy)|do you approve|confirm authorization",
    re.IGNORECASE,
)
RESUME_PROMPT = (
    "CLI-only E2E 계속. 최신 WORK_STATE와 증거로 미완료 PARTIAL 중 실행 가능한 "
    "첫 assertion만 선택해 검증하고 결과를 즉시 ledger/report에 기록해. "
    "기존 PASS/SCOPED_PASS/성능 baseline 반복 금지, 결함은 FAIL 증거로 유지하고 "
    "제품 코드는 수정하지 마. Server=frp-e2e-server(.113), 접속 가능한 Linux Agent만 "
    "사용; Windows/macOS 임시 제외. 호스트·인증·보안 차단은 우회하지 말고 "
    "그 항목만 BLOCKED로 기록해 다음 독립 항목 진행. "
    "명령별 timeout, 안전한 정리, 사용자 입력 대기 금지."
)


def run_command(argv, timeout=8):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)


def load_ledger(run_dir):
    path = run_dir / "SCENARIO_TRACKER.tsv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    ids = [row["SCENARIO_ID"] for row in rows]
    if len(rows) != 116 or len(set(ids)) != 116:
        raise ValueError("unsafe ledger: expected 116 unique scenario IDs")
    if any(not row.get("WORK_STATE") for row in rows):
        raise ValueError("unsafe ledger: missing WORK_STATE")
    unknown = {row["WORK_STATE"] for row in rows} - TERMINAL - PARTIAL - BLOCKED
    if unknown:
        raise ValueError("unsafe ledger: unknown WORK_STATE " + repr(sorted(unknown)))
    grouped = {"pass": [], "fail": [], "measured": [], "excluded": [],
               "partial": [], "blocked": []}
    for row in rows:
        sid, state = row["SCENARIO_ID"], row["WORK_STATE"]
        if state in PARTIAL:
            grouped["partial"].append(sid)
        elif state in BLOCKED:
            grouped["blocked"].append(sid)
        elif state == "SCENARIO_FAIL_REPRODUCED":
            grouped["fail"].append(sid)
        elif state == "MEASURED_NOT_QUALIFIED":
            grouped["measured"].append(sid)
        elif state == "EXCLUDED_AI_MCP":
            grouped["excluded"].append(sid)
        else:
            grouped["pass"].append(sid)
    digest = hashlib.sha256(
        "\n".join(f'{r["SCENARIO_ID"]}:{r["WORK_STATE"]}' for r in rows).encode()
    ).hexdigest()
    return grouped, digest


def ui_status(terminal):
    tail = "\n".join(terminal.splitlines()[-23:])
    if APPROVAL.search(tail):
        return "approval_pending"
    if "Goal paused (/goal resume)" in tail:
        return "paused"
    if "Goal stalled (/goal resume)" in tail:
        return "stalled"
    if "Pursuing goal" in tail:
        return "active"
    return "unknown"


def tmux_state(target, command=run_command):
    pane = command(["tmux", "capture-pane", "-t", target, "-p", "-S", "-90"])
    if pane.returncode:
        return "missing", "", ""
    program = command(["tmux", "display-message", "-t", target, "-p",
                       "#{pane_current_command}"])
    if program.returncode:
        return "unknown", pane.stdout, ""
    return ui_status(pane.stdout), pane.stdout, program.stdout.strip()


def codex_running(command=run_command):
    proc = command(["ps", "-u", str(os.getuid()), "-o", "args="])
    if proc.returncode:
        return None
    return any(re.search(r"/(?:bin/)?codex(?:\s+-c|\s+resume\b)", line)
               for line in proc.stdout.splitlines())


def read_state(path):
    try:
        with path.open(encoding="utf-8") as f:
            state = json.load(f)
            if not isinstance(state, dict):
                raise ValueError("state must be dict")
            return state
    except FileNotFoundError:
        return {"digest": "", "attempts": 0, "last_attempt": 0}


def write_json(path, payload):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def log_event(path, event):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def send_literal(target, content, command=run_command):
    for args in ([ "tmux", "send-keys", "-t", target, "-l", content],
                 [ "tmux", "send-keys", "-t", target, "Enter" ]):
        result = command(args)
        if result.returncode:
            raise RuntimeError(f"tmux send failed (rc={result.returncode})")


def recover_stalled(target, selected_scenario, command=run_command):
    prompt = (
        f"우선 검사 시나리오: {selected_scenario}. " + RESUME_PROMPT +
        " 이 항목이 실제로 불가하면 근거를 기록하고 다음 독립 작업으로 이동."
    )
    send_literal(target, prompt, command)
    result = command(["tmux", "send-keys", "-t", target, "Tab"])
    if result.returncode:
        raise RuntimeError("tmux queue failed")
    send_literal(target, "/goal resume", command)
    result = command(["tmux", "send-keys", "-t", target, "Tab"])
    if result.returncode:
        raise RuntimeError("tmux resume failed")


def relaunch_exact_session(target, run_dir, cwd, codex_bin, command=run_command):
    thread = (run_dir / "thread.id").read_text(encoding="utf-8").strip()
    uuid.UUID(thread)
    if not Path(codex_bin).is_file() or not Path(cwd).is_dir():
        raise RuntimeError("missing exact Codex executable or work directory")
    # No shell interpolation from a model: fixed paths and UUID-validated session.
    cmd = f"cd {cwd} && {codex_bin} resume {thread}"
    send_literal(target, cmd, command)


def evaluate(run_dir, target, state, ui, pane_program, running, now,
             cooldown=900, max_attempts=2, relaunch=False):
    grouped, digest = load_ledger(run_dir)
    if digest != state.get("digest"):
        state["digest"] = digest
    eligible = grouped["partial"]
    attempts_by_target = dict(state.get("attempts_by_target", {}))
    attempts_by_target = {k: int(v) for k, v in attempts_by_target.items()
                          if k in eligible}
    state["attempts_by_target"] = attempts_by_target
    selected = next((sid for sid in eligible
                     if attempts_by_target.get(sid, 0) < max_attempts), None)
    action, reason = "observe", "actor active; continue autonomous testing"
    if not eligible:
        action, reason = "none", "no pending PARTIAL; blocked/failed cases retained"
    elif selected is None:
        action, reason = "hold", "each partial scenario exhausted its bounded resume budget"
    elif ui == "approval_pending":
        action, reason = "hold", "approval pending; never automate consent"
    elif ui == "paused":
        action, reason = "hold", "deliberate pause; never auto-unpause"
    elif running is None:
        action, reason = "hold", "unable to verify actor process"
    elif not running:
        if relaunch and ui not in {"missing", "approval_pending", "paused"} and pane_program in {
            "bash", "zsh", "sh", "fish",
        }:
            action, reason = "relaunch", "verified actor exited and pane returned to shell"
        else:
            action, reason = "hold", "actor missing; no replacement unless exact session safe"
    elif ui == "active":
        pass
    elif ui == "stalled" and pane_program in {"codex", "codex-linux-x64"}:
        action, reason = "resume", f"stalled Codex with runnable partial assertion {selected}"
    elif ui == "stalled":
        action, reason = "hold", "stalled UI but pane is not owned by Codex"
    else:
        action, reason = "hold", "UI state not authoritative; fail closed"
    if action in {"resume", "relaunch"}:
        if now - float(state.get("last_attempt", 0)) < cooldown:
            action, reason = "cooldown", "prior resume within cooldown"
    report = {
        "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "ui": ui, "pane_program": pane_program, "actor_running": running,
        "counts": {key: len(value) for key, value in grouped.items()},
        "pending_ids": eligible, "blocked_ids": grouped["blocked"],
        "selected_scenario": selected, "digest": digest,
        "action": action, "reason": reason,
        "attempts": int(state.get("attempts", 0)),
        "target_attempts": attempts_by_target.get(selected, 0) if selected else 0,
    }
    return action, report


def tick(args, command=run_command, now=None):
    now = time.time() if now is None else now
    run_dir = Path(args.run_dir)
    state_path = run_dir / "e2e_watchdog_state.json"
    lock_path = run_dir / "e2e_watchdog.lock"
    guard = contextlib.nullcontext(None) if args.mode == "status" else lock_path.open("a+")
    with guard as lock:
        if lock is not None:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"action": "hold", "reason": "another watchdog owns lock"}
        state = read_state(state_path)
        ui, _screen, pane_command = tmux_state(args.tmux_target, command)
        active = codex_running(command)
        action, report = evaluate(
            run_dir, args.tmux_target, state, ui, pane_command, active, now,
            args.cooldown_seconds, args.max_attempts, args.allow_relaunch,
        )
        if args.mode != "status":
            state.update(digest=report["digest"], last_ui=ui,
                         last_seen=report["time_utc"])
            if action in {"resume", "relaunch"}:
                # Persist the attempt before interacting: crash can't cause duplicate resumption.
                state["last_attempt"] = now
                state["attempts"] = int(state.get("attempts", 0)) + 1
                target = report["selected_scenario"]
                by_target = dict(state.get("attempts_by_target", {}))
                by_target[target] = by_target.get(target, 0) + 1
                state["attempts_by_target"] = by_target
                write_json(state_path, state)
                try:
                    if action == "resume":
                        recover_stalled(args.tmux_target, target, command)
                    else:
                        relaunch_exact_session(args.tmux_target, run_dir,
                                               args.cwd, args.codex_binary, command)
                    report["executed"] = True
                except Exception as exc:
                    report["executed"] = False
                    report["error"] = f"{type(exc).__name__}: {exc}"
            else:
                write_json(state_path, state)
            report["attempts"] = state.get("attempts", 0)
            target = report.get("selected_scenario")
            report["target_attempts"] = state.get("attempts_by_target", {}).get(target, 0)
            write_json(run_dir / "e2e_watchdog_status.json", report)
            log_event(run_dir / "e2e_watchdog_events.jsonl", {
                key: report[key] for key in ("time_utc", "action", "reason", "counts",
                                            "attempts", "ui", "selected_scenario")
            })
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["status", "once", "watch"])
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN))
    parser.add_argument("--tmux-target", default="codex:0.0")
    parser.add_argument("--cwd", default="/home/aella/datarelay-link-main")
    parser.add_argument("--codex-binary",
                        default="/home/aella/.nvm/versions/node/v22.23.2/bin/codex")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--cooldown-seconds", type=int, default=900)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--allow-relaunch", action="store_true")
    args = parser.parse_args()
    if args.interval_seconds < 20 or args.max_attempts < 0 or args.cooldown_seconds < 60:
        parser.error("unsafe scheduling parameters")
    if args.mode != "watch":
        try:
            print(json.dumps(tick(args), ensure_ascii=False, sort_keys=True))
        except Exception as exc:
            print(json.dumps({"action": "error", "reason": str(exc)}))
            return 1
        return 0
    while True:
        try:
            report = tick(args)
            print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"action": "error", "reason": str(exc)}), flush=True)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
