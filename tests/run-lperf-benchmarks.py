#!/usr/bin/env python3
"""LPERF source-bound local benchmark runner. No installed services are modified.

MCP exercises 100 synthetic AgentLoop identities with a separate bridge supervisor,
agent-facing server processes and Agent processes. Egress exercises a disposable
loopback gateway and origin with compiled temporary Internet Access rules.

"mixed" shares host CPU, NOT one product Server process: it is an early contention
screen, not acceptance evidence for LPERF-3 or a Real User E2E substitute.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tests" / "test-mcp-bridge-scale-target.py"
EGRESS = ROOT / "tests" / "run-egress-benchmark.py"


def _integers(text: str, maximum: int) -> list[int]:
    try:
        values = [int(x) for x in text.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not values or len(values) > 9 or any(x < 1 or x > maximum for x in values):
        raise argparse.ArgumentTypeError("each value must be 1..%d (up to 9 entries)" % maximum)
    return values


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def _mem_total_kib() -> int | None:
    try:
        match = re.search(r"^MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)
        return int(match.group(1)) if match else None
    except OSError:
        return None


def _kv(text: str, marker: str) -> dict[str, str]:
    lines = [line for line in text.splitlines() if marker in line]
    if not lines:
        return {}
    line = lines[-1].split(marker, 1)[-1] if marker == "SCALE_METRICS" else lines[-1]
    return dict(re.findall(r"([A-Za-z][A-Za-z_0-9]*)=([^\s]+)", line))


def _execute(name: str, command: list[str], env: dict[str, str], dest: Path, timeout: int) -> dict:
    start = time.monotonic()
    outcome = {"name": name, "argv": command, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        outcome["returncode"] = rc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        outcome["returncode"] = 124
        outcome["timed_out"] = True
    outcome["elapsed_s"] = round(time.monotonic() - start, 3)
    (dest / (name + ".stdout.log")).write_text(stdout)
    (dest / (name + ".stderr.log")).write_text(stderr)
    output = stdout + "\n" + stderr
    if name.startswith("mcp_"):
        outcome["metrics"] = _kv(output, "SCALE_METRICS")
        p95 = outcome["metrics"].get("p95_ms")
        if outcome["returncode"] == 0:
            outcome["status"] = "PASS_LOCAL"
        elif p95 and float(p95) > 500:
            outcome["status"] = "SLO_UNMET"
        else:
            outcome["status"] = "FAILED"
        outcome["topology"] = "100 synthetic AgentLoop hosts; local separate Agent/Bridge processes"
    else:
        outcome["metrics"] = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", output, re.M))
        outcome["status"] = "PASS_LOCAL" if outcome["returncode"] == 0 and "PERFORMANCE_BENCHMARK=PASS" in output else "FAILED"
        outcome["topology"] = "disposable loopback gateway+origin; stub DNS/connect"
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mcp", "egress", "both", "mixed"), default="both")
    parser.add_argument("--mcp-calls", type=lambda x: _integers(x, 30), default=[1, 10, 30])
    parser.add_argument("--egress-connections", type=lambda x: _integers(x, 100), default=[10, 50, 100])
    parser.add_argument("--workers", type=int, default=1, help="isolated Bridge worker process count")
    parser.add_argument("--agent-procs", type=int, default=5)
    parser.add_argument("--agent-server-procs", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--transfer-kib", type=int, default=128)
    parser.add_argument("--mcp-target", choices=("one", "spread"), default="spread")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not (1 <= args.workers <= 12 and 1 <= args.agent_procs <= 10
            and 1 <= args.agent_server_procs <= 6 and 1 <= args.rounds <= 10
            and 0 <= args.transfer_kib <= 8192 and 10 <= args.timeout <= 900):
        parser.error("worker/process/round/transfer/timeout outside bounded safety range")
    dest = args.output_dir.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        parser.error("output directory must be empty, to preserve raw prior evidence")
    report = {
        "source_head": _git("rev-parse", "HEAD"),
        "source_dirty": bool(_git("status", "--porcelain")),
        "source_branch": _git("branch", "--show-current"),
        "host": platform.node(),
        "logical_cpus": os.cpu_count(),
        "mem_total_kib": _mem_total_kib(),
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": args.mode,
        "release_qualified": False,
        "real_user_e2e": "NOT_RUN",
        "mixed_same_link_server": False,
        "results": [],
    }
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    def make_mcp(calls: int) -> tuple[list[str], dict[str, str]]:
        env_case = dict(env, SCALE_AGENT_PROCS=str(args.agent_procs),
                        SCALE_SERVER_PROCS=str(args.agent_server_procs),
                        SCALE_BRIDGE_PROCS=str(args.workers), SCALE_CALLS=str(calls),
                        SCALE_ROUNDS=str(args.rounds))
        case = "test_thirty_calls_spread_over_thirty_hosts_all_succeed_quickly" if args.mcp_target == "spread" else "test_thirty_simultaneous_calls_all_succeed_quickly"
        return [sys.executable, str(MCP), "MCPBridgeScaleTargetTests." + case], env_case
    def make_egress(conns: int) -> tuple[list[str], dict[str, str]]:
        return [sys.executable, str(EGRESS), "--concurrency", str(conns),
                "--transfer-kib", str(args.transfer_kib), "--hold-ms", "200"], env
    # Mixed is intentionally a same-host smoke screen only, not an independent
    # completion claim about shared Server/allocator/Bridge dispatch.
    if args.mode == "mixed":
        from concurrent.futures import ThreadPoolExecutor
        mcp_cmd, mcp_env = make_mcp(args.mcp_calls[-1])
        eg_cmd, eg_env = make_egress(args.egress_connections[-1])
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_m = pool.submit(_execute, "mcp_mixed", mcp_cmd, mcp_env, dest, args.timeout)
            future_e = pool.submit(_execute, "egress_mixed", eg_cmd, eg_env, dest, args.timeout)
            report["results"].extend((future_m.result(), future_e.result()))
    else:
        if args.mode in ("mcp", "both"):
            for n in args.mcp_calls:
                cmd, runenv = make_mcp(n)
                report["results"].append(_execute("mcp_%02d" % n, cmd, runenv, dest, args.timeout))
        if args.mode in ("egress", "both"):
            for n in args.egress_connections:
                cmd, runenv = make_egress(n)
                report["results"].append(_execute("egress_%03d" % n, cmd, runenv, dest, args.timeout))
    report["all_local_tests_passed"] = all(x["status"] == "PASS_LOCAL" for x in report["results"])
    report_path = dest / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for x in report["results"]:
        print("%s %s p95=%s elapsed_s=%s" % (
            x["name"], x["status"],
            x["metrics"].get("p95_ms", x["metrics"].get("CONNECT_P95_MS", "n/a")),
            x["elapsed_s"]), flush=True)
    print("LPERF_REPORT=%s" % report_path)
    return 0 if report["all_local_tests_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
