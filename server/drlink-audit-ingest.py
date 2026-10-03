#!/usr/bin/env python3
"""Bounded Data Relay Link 3.0 audit spool ingestor."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load():
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "lib",
        here.parent,
        Path("/usr/local/lib/drlink"),
    ]
    root = os.environ.get("DRLINK_TEST_ROOT") or os.environ.get("FRP_DEPLOY_TEST_ROOT")
    if root:
        candidates.insert(0, Path(root) / "usr/local/lib/drlink")
    for path in candidates:
        if (path / "drlink_v30_audit.py").is_file():
            sys.path.insert(0, str(path))
            break
    from drlink_control_db import runtime_dir, utc_now_iso  # noqa: E402
    from drlink_control_plane import ControlPlane  # noqa: E402
    from drlink_v30_audit import (  # noqa: E402
        AuditIngestor,
        DurableAuditSpool,
        default_access_spool_root,
    )
    return runtime_dir, utc_now_iso, ControlPlane, AuditIngestor, DurableAuditSpool, default_access_spool_root


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def main() -> int:
    (
        runtime_dir,
        utc_now_iso,
        ControlPlane,
        AuditIngestor,
        DurableAuditSpool,
        default_access_spool_root,
    ) = _load()
    root = os.environ.get("DRLINK_TEST_ROOT") or os.environ.get("FRP_DEPLOY_TEST_ROOT") or None
    try:
        max_segments = int(os.environ.get("DRLINK_AUDIT_INGEST_SEGMENTS", "4"))
    except ValueError:
        max_segments = 4
    max_segments = max(1, min(max_segments, 32))

    plane = ControlPlane(root)
    overall_ok = True
    sources = {}
    try:
        for access_plane, source in (
            ("remote", "remote-access"),
            ("internet", "internet-access"),
        ):
            spool = DurableAuditSpool(
                default_access_spool_root(access_plane, root),
                source,
            )
            try:
                result = AuditIngestor(plane.conn, spool).ingest(
                    max_segments=max_segments
                )
                sources[source] = {
                    "ok": True,
                    "result": result,
                }
            except Exception as exc:
                overall_ok = False
                sources[source] = {
                    "ok": False,
                    "error": str(exc)[:1000],
                    "health": spool.health(),
                }
        status = {
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "ok": overall_ok,
            "sources": sources,
        }
        _atomic_json(runtime_dir(root) / "audit-ingest.json", status)
    finally:
        plane.close()

    sys.stdout.write(
        "AUDIT_INGEST=%s\n" % ("PASS" if overall_ok else "DEGRADED")
    )
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
