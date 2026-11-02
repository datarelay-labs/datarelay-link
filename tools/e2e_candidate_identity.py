#!/usr/bin/env python3
"""Fail-closed installed-source binding for immutable E2E candidates.

A generated-only provenance commit is a distinct HEAD. Installed product
"Source HEAD" is the content parent, while the E2E candidate is the child.
This module never treats an arbitrary ancestor, sibling, or modified bundle as
equivalent to the candidate.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"^[0-9a-f]{40}$")
# Keep aligned with scripts/check-release-attest-binding.py, with a
# regression checking the same allowlist on each side.
PROVENANCE_PATHS = frozenset({
    "SHA256SUMS",
    "release-manifest.json",
    "dist/bootstrap-client.sh",
    "dist/bootstrap-server.sh",
    "dist/bootstrap-client.ps1",
    "dist/uninstall-client.sh",
    "dist/uninstall-server.sh",
    "dist/sbom.spdx.json",
})


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True, capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("cannot inspect immutable candidate Git object") from exc
    if proc.returncode != 0:
        raise ValueError("candidate Git object unavailable: " + proc.stderr.strip()[:200])
    return proc.stdout.strip()


def bound_installed_head(repo: Path, candidate_head: str, installed_head: str) -> str:
    """Return 'exact' or 'provenance-parent'; raise on unsafe/mismatched binding.

    This checks Git's committed objects, *not* an uncommitted worktree or a
    mutable manifest file. Runtime identity must be observed independently
    through the actual product CLI and retained with the E2E evidence.
    """
    if not SHA.fullmatch(candidate_head or "") or not SHA.fullmatch(installed_head or ""):
        raise ValueError("candidate and installed Source HEAD must be exact lowercase 40-hex SHAs")
    if _git(repo, "rev-parse", "--verify", candidate_head + "^{commit}") != candidate_head:
        raise ValueError("candidate does not resolve to the claimed commit")
    if installed_head == candidate_head:
        return "exact"
    parent = _git(repo, "rev-parse", "--verify", candidate_head + "^1")
    if installed_head != parent:
        raise ValueError("installed Source HEAD is not the candidate's first content parent")
    manifest = json.loads(_git(repo, "show", candidate_head + ":release-manifest.json"))
    if manifest.get("source_head") != parent or manifest.get("git_ref") != parent:
        raise ValueError("candidate manifest source_head/git_ref does not match content parent")
    if manifest.get("immutable_source_ref") != parent:
        raise ValueError("candidate manifest immutable_source_ref mismatch")
    changed = _git(repo, "diff", "--name-status", "--no-renames", parent, candidate_head)
    paths = set()
    for line in changed.splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] not in {"M", "A"}:
            raise ValueError("candidate provenance commit contains non-add/modify change")
        paths.add(fields[1])
    if not paths or "release-manifest.json" not in paths or not paths.issubset(PROVENANCE_PATHS):
        raise ValueError("candidate provenance commit changes product or unsupported paths")
    return "provenance-parent"
