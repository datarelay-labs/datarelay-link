#!/usr/bin/env python3
"""Non-mutating inventory of DataRelay Link Git worktrees.

This tool never removes worktrees, prunes refs, resets changes, or runs product
tests. A cleanup candidate is only a review item, not deletion permission.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def git(repo: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", repo, *args],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=25, check=False,
    )


def parse_worktrees(data: str) -> list[dict]:
    """Parse porcelain records, including detached/locked/prunable states."""
    records: list[dict] = []
    for block in data.strip().split("\n\n"):
        if not block:
            continue
        result: dict = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree":
                result["path"] = value
            elif key == "HEAD":
                result["head"] = value
            elif key == "branch":
                result["branch"] = value.removeprefix("refs/heads/")
            elif key in ("detached", "locked", "prunable", "bare"):
                result[key] = value or True
        if result.get("path"):
            records.append(result)
    return records


def active_process_refs(paths: list[str]) -> dict[str, list[int]] | None:
    """Best-effort /proc visibility. Unknown is never treated as safe."""
    proc = Path("/proc")
    if not proc.exists():
        return None
    hits: dict[str, set[int]] = {path: set() for path in paths}
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            pid = int(p.name)
            cwd = os.readlink(p / "cwd")
            cmdline = (p / "cmdline").read_bytes()[:16384].replace(b"\0", b" ")
        except (OSError, PermissionError, ProcessLookupError):
            continue
        for path in paths:
            if cwd == path or cwd.startswith(path + os.sep) or os.fsencode(path) in cmdline:
                hits[path].add(pid)
    return {path: sorted(pids) for path, pids in hits.items()}


def workspace_paths(index: str | None) -> set[str]:
    if not index:
        return set()
    index_path = Path(index)
    if not index_path.is_file() or index_path.is_symlink():
        raise OSError("explicit workspace index missing or unsafe")
    content = index_path.read_text(encoding="utf-8")
    return set(re.findall(r"`(/[^\n`]+)`", content))


def inventory(repo: str, ref: str, index: str | None, scan_processes: bool) -> dict:
    repo_path = str(Path(repo).resolve(strict=True))
    head = git(repo_path, "rev-parse", ref)
    worktrees = git(repo_path, "worktree", "list", "--porcelain")
    if head.returncode or worktrees.returncode:
        raise RuntimeError("cannot resolve reference or worktrees")
    main_sha = head.stdout.strip()
    entries = parse_worktrees(worktrees.stdout)
    index_entries = workspace_paths(index)
    paths = [e["path"] for e in entries]
    live = active_process_refs(paths) if scan_processes else None
    counts: dict[str, int] = {}
    for e in entries:
        path = e["path"]
        e["exists"] = Path(path).is_dir()
        e["linked_in_workspace_index"] = path in index_entries
        e["frozen_evidence_path"] = "/drlink-validation/" in path
        e["process_refs"] = live.get(path, []) if live is not None else None
        e["tracked_modified_or_untracked"] = None
        e["ignored_files"] = None
        if e["exists"]:
            status = git(path, "status", "--porcelain=v1", "--untracked-files=all")
            ignored = git(path, "ls-files", "--others", "-i", "--exclude-standard")
            if status.returncode == 0:
                e["tracked_modified_or_untracked"] = len(status.stdout.splitlines())
            if ignored.returncode == 0:
                e["ignored_files"] = len(ignored.stdout.splitlines())
        merged = git(repo_path, "merge-base", "--is-ancestor", e.get("head", ""), main_sha)
        e["head_in_main"] = merged.returncode == 0
        reasons = []
        if not e["exists"] or Path(path).is_symlink():
            reasons.append("ABSENT_OR_SYMLINK")
        if e.get("branch"):
            reasons.append("BRANCH_CHECKOUT")
        if e.get("locked") or e.get("prunable") or e.get("bare"):
            reasons.append("GIT_SPECIAL_STATE")
        if e["tracked_modified_or_untracked"] is None or e["tracked_modified_or_untracked"] > 0:
            reasons.append("DIRTY_OR_UNKNOWN")
        if e["ignored_files"] is None or e["ignored_files"] > 0:
            reasons.append("IGNORED_OR_UNKNOWN")
        if e["process_refs"] is None:
            reasons.append("PROCESS_VISIBILITY_UNKNOWN")
        elif e["process_refs"]:
            reasons.append("PROCESS_REFERENCES")
        if e["linked_in_workspace_index"]:
            reasons.append("WORKSPACE_INDEX_REFERENCE")
        if e["frozen_evidence_path"]:
            reasons.append("FROZEN_EVIDENCE")
        if not e["head_in_main"]:
            reasons.append("HEAD_NOT_IN_MAIN")
        if path == repo_path:
            reasons.append("CANONICAL_CHECKOUT")
        if not path.startswith("/home/aella/datarelay-link-worktrees/"):
            reasons.append("OUTSIDE_REVIEW_PREFIX")
        e["protection_reasons"] = reasons
        e["disposition"] = "REVIEW_CANDIDATE_ONLY" if not reasons else (
            "PRESERVE_WIP" if "DIRTY_OR_UNKNOWN" in reasons or "IGNORED_OR_UNKNOWN" in reasons
            else "KEEP_OR_MANUAL_REVIEW"
        )
        counts[e["disposition"]] = counts.get(e["disposition"], 0) + 1
    return {
        "schema_version": 1,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": repo_path,
        "base_ref": ref,
        "base_head": main_sha,
        "process_scan": "BEST_EFFORT" if live is not None else "NOT_AVAILABLE",
        "worktree_count": len(entries),
        "dispositions": counts,
        "worktrees": entries,
        "note": "No automatic removal is authorized by this read-only report.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repository", required=True, help="Existing local Git checkout")
    p.add_argument("--base-ref", default="main")
    p.add_argument("--workspace-index", help="Existing retained checkout index")
    p.add_argument("--output", help="Optional private JSON evidence file")
    p.add_argument("--skip-process-scan", action="store_true", help="Test only; always retains uncertainty")
    args = p.parse_args()
    try:
        report = inventory(args.repository, args.base_ref, args.workspace_index, not args.skip_process_scan)
        data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.is_symlink():
                raise ValueError("refusing symlink output")
            tmp = target.with_name(target.name + f".{os.getpid()}.tmp")
            with open(tmp, "x", encoding="utf-8") as stream:
                os.chmod(tmp, 0o600)
                stream.write(data)
            os.replace(tmp, target)
            print(f"WORKTREE_AUDIT={target} COUNT={report['worktree_count']} {report['dispositions']}")
        else:
            sys.stdout.write(data)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"WORKTREE_AUDIT_ERROR={type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
