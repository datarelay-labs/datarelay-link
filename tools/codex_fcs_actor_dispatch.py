#!/usr/bin/env python3
"""Launch ONE genuine Codex persona actor for an owner-authorized NON-DESTRUCTIVE CLI FCS.

This is a test-actor launcher and receipt writer, not a scripted user or test
oracle. No Codex process can start until the caller supplies an actual lab
current public product identity and the canonical single-run audit lock. Never used for Full E2E
state-changing workflows. Run data/evidence must be private and outside /tmp.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
ALLOWED = {"DIRECT_USER", "AI_OPERATOR", "AI_ADVISER"}
SAFE_ID = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
UUID36 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def validate_launch(
    *,
    run_root: Path, run_id: str, pair_id: str, role: str,
    prompt_file: Path, preflight_file: Path | None, lock_file: Path,
    installed_source_head: str | None = None,
) -> dict:
    if not SAFE_ID.fullmatch(run_id) or not SAFE_ID.fullmatch(pair_id):
        raise ValueError("Invalid RUN_ID or PAIR_ID")
    if role not in ALLOWED:
        raise ValueError("Unknown Codex actor")
    if run_root.is_symlink():
        raise ValueError("RUN_ID root may not be a symlink")
    root = run_root.resolve()
    if root == Path("/tmp") or Path("/tmp") in root.parents:
        raise ValueError("Codex actor evidence may not use /tmp")
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Private persistent RUN_ID root is missing or a symlink")
    if root.stat().st_mode & 0o077:
        raise ValueError("RUN_ID evidence directory must be owner-private")
    # Global seven-host readiness is diagnostic. Unrelated unregistered
    # native hosts or blocked MCP/OAuth may not veto safe independent FCS.
    lab = {}
    if preflight_file is not None:
        if not preflight_file.is_file() or preflight_file.is_symlink():
            raise ValueError("Provided lab observation is missing or a symlink")
        lab = json.loads(preflight_file.read_text(encoding="utf-8"))
        if not isinstance(lab, dict):
            raise ValueError("Lab observation must be a JSON object")
    head = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        text=True, timeout=8,
    ).strip()
    if not HEX40.fullmatch(head):
        raise ValueError("Current repository HEAD is invalid")
    # A stale report may not silently pin a different candidate; the auditor
    # may instead supply the currently OBSERVED public CLI Source HEAD.
    if lab and lab.get("repo_head") != head and installed_source_head is None:
        raise ValueError("Preflight repo HEAD is stale; supply observed installed Source HEAD")
    installed = str(installed_source_head or lab.get("candidate_source_head") or "")
    if not HEX40.fullmatch(installed):
        raise ValueError("Pinned installed Source HEAD is required for this FCS run")
    if not lock_file.is_file() or lock_file.is_symlink():
        raise ValueError("Canonical FCS single-run lock is missing")
    lock = lock_file.read_text(encoding="utf-8")
    if ("RUN_ID=" + run_id) not in lock and ('"RUN_ID": "' + run_id + '"') not in lock:
        raise ValueError("FCS lock is not owned by the requested RUN_ID")
    prompt_path = prompt_file.resolve()
    if not prompt_path.is_relative_to(root) or prompt_file.is_symlink():
        raise ValueError("Actor prompt must be a private file inside this RUN_ID")
    if not prompt_path.is_file() or prompt_path.stat().st_mode & 0o077:
        raise ValueError("Actor prompt is missing or not private")
    prompt = prompt_path.read_bytes()
    if not 40 <= len(prompt) <= 100000:
        raise ValueError("Actor prompt size out of bounds")
    target = root / "actors" / pair_id / role
    if target.is_symlink() or target.exists():
        raise FileExistsError("This Codex actor already exists; use a new RUN_ID")
    return {
        "run_id": run_id, "pair_id": pair_id, "role": role,
        "repo_head": head, "source_head": installed,
        "scope": "NON_DESTRUCTIVE_FCS",
        "global_lab_status": lab.get("status", "NOT_PROVIDED"),
        "excluded_global_gates": lab.get("not_ready_gate_ids", []),
        "source_pin_origin": ("PUBLIC_OBSERVATION_DECLARED"
                              if installed_source_head else "LAB_OBSERVATION"),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "prompt_bytes": prompt,
        "target": target,
        "utc": utc(),
    }


def extract_receipt(event_file: Path, role: str) -> dict:
    thread_ids: list[str] = []
    completed = 0
    forbidden = []
    try:
        with event_file.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("type") == "thread.started":
                    thread_ids.append(str(event.get("thread_id") or ""))
                if event.get("type") == "turn.completed":
                    completed += 1
                item = event.get("item") or {}
                if (role == "AI_ADVISER" and isinstance(item, dict)
                        and item.get("type") not in (None, "agent_message", "reasoning")):
                    forbidden.append(str(item["type"]))
    except (OSError, ValueError, TypeError, UnicodeError):
        return {"status": "INVALID_JSONL", "thread_id": None}
    ok = (
        len(thread_ids) == 1 and bool(UUID36.fullmatch(thread_ids[0]))
        and completed >= 1 and not forbidden
    )
    return {
        "status": "STRUCTURAL_PASS" if ok else "STRUCTURAL_FAIL",
        "thread_id": thread_ids[0] if len(thread_ids) == 1 else None,
        "turns_completed": completed,
        "forbidden_ai_tool_types": sorted(set(forbidden)),
    }


def build_codex_command(codex: str, target: Path, last: Path,
                        role: str) -> list[str]:
    if role not in ALLOWED:
        raise ValueError("Unknown Codex actor")
    command = [codex, "exec"]
    if role == "AI_ADVISER":
        # Text-only adviser never needs SSH or the caller's tool configuration.
        # Its raw JSONL is also checked for ANY tool use, including new types.
        command += ["--ignore-user-config", "--sandbox", "read-only"]
    else:
        # Real Direct/AI User public SSH uses ordinary platform-reviewed access.
        command += ["--approve-for-me"]
    return command + [
        "--json", "--skip-git-repo-check", "--cd", str(target),
        "--output-last-message", str(last), "-",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--role", required=True, choices=sorted(ALLOWED))
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--preflight", type=Path,
                        help="Optional diagnostic lab inventory, never a global FCS gate")
    parser.add_argument("--installed-source-head",
                        help="Observed 40-hex Source HEAD on assigned actual test host")
    parser.add_argument("--max-seconds", type=int, default=3600)
    parser.add_argument("--lock", type=Path,
                        default=REPO / "e2e-reports/.cli-feature-scenario.lock")
    args = parser.parse_args()
    if not 60 <= args.max_seconds <= 14400:
        parser.error("--max-seconds must be 60..14400")
    try:
        ready = validate_launch(
            run_root=args.run_root, run_id=args.run_id, pair_id=args.pair_id,
            role=args.role, prompt_file=args.prompt_file,
            preflight_file=args.preflight, lock_file=args.lock,
            installed_source_head=args.installed_source_head,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("CODEX_ACTOR_BLOCKED=" + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 3
    codex = shutil.which("codex")
    if codex is None:
        print("CODEX_ACTOR_BLOCKED=Codex binary not installed", file=sys.stderr)
        return 3
    # The auditor may launch Codex, but the launcher NEVER selects, replays
    # or generates public user commands. Each model gets only its own prompt.
    target: Path = ready["target"]
    target.mkdir(parents=True, mode=0o700, exist_ok=False)
    target.chmod(0o700)
    events = target / "codex-events.jsonl"
    errors = target / "codex-stderr.log"
    last = target / "last-message.txt"
    status = target / "receipt.json"
    with events.open("x", encoding="utf-8") as out, errors.open("x", encoding="utf-8") as err:
        os.chmod(events, 0o600)
        os.chmod(errors, 0o600)
        args_cmd = build_codex_command(codex, target, last, args.role)
        started = {"run_id": ready["run_id"], "pair_id": ready["pair_id"],
                   "role": ready["role"], "status": "STARTING", "start_utc": ready["utc"],
                   "source_head": ready["source_head"],
                   "repo_head": ready["repo_head"],
                   "scope": ready["scope"],
                   "global_lab_status": ready["global_lab_status"],
                   "excluded_global_gates": ready["excluded_global_gates"],
                   "source_pin_origin": ready["source_pin_origin"],
                   "prompt_sha256": ready["prompt_sha256"]}
        status.write_text(json.dumps(started, indent=2) + "\n")
        status.chmod(0o600)
        proc = None
        try:
            proc = subprocess.Popen(
                args_cmd, stdin=subprocess.PIPE, stdout=out, stderr=err,
                cwd=target,
            )
            started["pid"] = proc.pid
            started["status"] = "RUNNING"
            status.write_text(json.dumps(started, indent=2) + "\n")
            try:
                proc.communicate(input=ready["prompt_bytes"],
                                 timeout=args.max_seconds)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                started["status"] = "TIMEOUT"
                started["error_class"] = "CODEX_ACTOR_TIMEOUT"
                status.write_text(json.dumps(started, indent=2) + "\n")
                print("CODEX_ACTOR_TIMEOUT; no persona PASS",
                      file=sys.stderr)
                return 2
            exit_code = proc.returncode
        except (OSError, subprocess.SubprocessError) as exc:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
            started["status"] = "EXECUTION_ERROR"
            started["error_class"] = type(exc).__name__
            status.write_text(json.dumps(started, indent=2) + "\n")
            print("CODEX_ACTOR_ERROR=" + type(exc).__name__, file=sys.stderr)
            return 2
    raw_receipt = extract_receipt(events, args.role)
    finished = {**started, **raw_receipt,
                "finish_utc": utc(), "exit_code": exit_code,
                "events_sha256": hashlib.sha256(events.read_bytes()).hexdigest()}
    if exit_code:
        finished["status"] = "CODEX_FAILED"
    status.write_text(json.dumps(finished, indent=2) + "\n")
    if last.exists():
        last.chmod(0o600)
    # Never print model output, input prompt or raw logs (may contain credentials).
    print(json.dumps({
        "role": args.role, "pair_id": args.pair_id,
        "result": finished["status"], "thread_id": finished.get("thread_id"),
        "codex_exit": exit_code,
        "evidence": str(status),
    }))
    return 0 if finished["status"] == "STRUCTURAL_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
