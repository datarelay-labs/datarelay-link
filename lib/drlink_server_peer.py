#!/usr/bin/env python3
"""DRLink Server-as-Managed-Host MCP peer, without installing an Agent.

Uses the existing DRLink signed management job transport and an ISOLATED
enrolled Server-peer identity, never /etc/frp or an Agent service. The
central Server owns AI Identity/AI Access admission; this peer independently
enforces a strict local capability/path/OS-privilege ceiling.

This module deliberately does NOT issue, copy or invent enrollment credentials.
An authorized central operator must enroll this Server as a Managed Host using
a distinct cryptographic identity and an ordinary one-use Enrollment Code.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import stat
import sys
import threading
import time
from urllib.parse import urlparse

import drlink_mgmt_sync as management
import drlink_v24 as v24
from drlink_control_plane import path_allowed
from drlink_ai_agent import _deadline_passed
from drlink_mcp_server_executor import ExecutorDenied, execute_as_unprivileged_user

SERVER_PEER_ROLE = "drlink-server-peer"
LOCAL_POLL_SECONDS = 2.0
LOCAL_BACKOFF_SECONDS = 5.0
MAX_JOBS_PER_CLAIM = 4


class ServerPeerDenied(Exception):
    pass


def _confined_regular_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    return stat.S_ISREG(path.stat().st_mode)


def validate_peer_root(root: str) -> dict:
    """Separate enrolled Server-peer tree; never the host Agent install state."""
    base = Path(str(root or ""))
    if str(os.environ.get("DRLINK_MGMT_INSECURE") or "").lower() in ("1", "yes", "true"):
        raise ServerPeerDenied("Insecure management TLS is forbidden for a Server Peer")
    if not base.is_absolute() or str(base) in ("/", "/etc", "/etc/frp", "/var/lib/drlink"):
        raise ServerPeerDenied("An isolated absolute Server-peer state root is required")
    if base.is_symlink() or not base.is_dir():
        raise ServerPeerDenied("Server-peer state root is missing or is a symlink")
    if base.stat().st_mode & 0o077:
        raise ServerPeerDenied("Server-peer state root must not be accessible to group/other")
    # An unprivileged worker may read its own files, but other identities may
    # not. Host-wide shared Agent/Server credentials must never be imported.
    if base.stat().st_uid != os.geteuid():
        raise ServerPeerDenied("Server-peer state root ownership mismatch")
    marker = base / "server-peer.json"
    state = base / "etc/frp/client-state.json"
    key = base / "etc/frp/client-identity.key"
    mac = base / "etc/frp/client-identity.mac"
    endpoint = base / "etc/frp/server-endpoint.json"
    for item in (marker, state, key, mac, endpoint):
        if not _confined_regular_file(item) or item.stat().st_mode & 0o077:
            raise ServerPeerDenied("Enrolled Server-peer identity is missing or accessible to others")
    try:
        info = json.loads(marker.read_text("utf-8"))
        identity = json.loads(state.read_text("utf-8"))
        target = json.loads(endpoint.read_text("utf-8"))
    except (ValueError, OSError):
        raise ServerPeerDenied("Server-peer state is invalid") from None
    if not isinstance(info, dict) or info.get("role") != SERVER_PEER_ROLE:
        raise ServerPeerDenied("Server-peer role marker is missing")
    if not isinstance(identity, dict) or not str(identity.get("machine_id") or ""):
        raise ServerPeerDenied("An enrolled machine identity is required")
    if info.get("machine_id") != identity.get("machine_id"):
        raise ServerPeerDenied("Server-peer role is not bound to enrolled identity")
    if not isinstance(target, dict):
        raise ServerPeerDenied("Central management endpoint is invalid")
    url = str(target.get("mgmt_url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ServerPeerDenied("Server-peer management endpoint must use authenticated HTTPS")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ServerPeerDenied("Server-peer management endpoint must be an HTTPS origin")
    if info.get("central_origin") != url.rstrip("/"):
        raise ServerPeerDenied("Enrolled Server-peer origin does not match central trust binding")
    if str(management.resolve_mgmt_base_url(str(base)) or "") != url.rstrip("/"):
        raise ServerPeerDenied("Management endpoint resolution is inconsistent")
    try:
        import frp_mgmt_auth as mgmt_auth
        mgmt_auth.validate_private_key(key)
    except Exception:
        raise ServerPeerDenied("Server-peer signing key is invalid") from None
    return {"machine_id": identity["machine_id"], "central_origin": url.rstrip("/"),
            "root": str(base)}


def _local_file_enabled(capability: str) -> bool:
    if capability in ("read_file", "download_file"):
        return os.environ.get("DRLINK_SERVER_PEER_READ_ENABLED") == "1"
    return False


def execute_peer_job(job: dict) -> dict:
    """No shell parsing, no Agent execute_local, no root-level file access."""
    if not isinstance(job, dict):
        return {"result": "DENY", "error": "Invalid Server-peer job"}
    cap = str(job.get("capability") or "")
    args = job.get("arguments") or {}
    if not isinstance(args, dict):
        return {"result": "DENY", "error": "Invalid Server-peer arguments"}
    if _deadline_passed(job.get("deadline_at")):
        return {"result": "DENY", "error": "Server-peer job deadline expired"}
    if cap == "get_system_info":
        sysinfo = os.uname()
        return {"result": "ALLOW", "sysname": sysinfo.sysname,
                "nodename": sysinfo.nodename, "release": sysinfo.release,
                "machine": sysinfo.machine}
    if cap in ("read_file", "download_file") and _local_file_enabled(cap):
        path = str(args.get("path") or "")
        patterns = job.get("patterns")
        # Central AI Access scope AND the independent local executor roots must
        # both permit the target; a missing remote pattern never means ALL.
        if not isinstance(patterns, list) or not patterns or not path_allowed(path, patterns):
            return {"result": "DENY", "error": "Server-peer file path denied"}
        try:
            payload = execute_as_unprivileged_user({"action": "read_file", "path": path})
        except (ExecutorDenied, OSError, ValueError, TypeError):
            return {"result": "DENY", "error": "Server-peer local executor denied the operation"}
        return {"result": "ALLOW", **payload}
    return {"result": "DENY", "error": "Server-peer capability disabled"}


class ServerPeerLoop:
    """Only outbound signed job claims, owned by a separate enrolled identity."""

    def __init__(self, root: str, *, stop_event=None):
        self.root = str(root)
        self.stop_event = stop_event or threading.Event()

    def run_once(self) -> int:
        validate_peer_root(self.root)
        if os.environ.get("DRLINK_SERVER_PEER_ENABLED") != "1":
            raise ServerPeerDenied("Server-peer polling is disabled")
        reply = management.claim_ai_jobs_on_server(root=self.root, limit=MAX_JOBS_PER_CLAIM)
        if not isinstance(reply, dict):
            raise ServerPeerDenied("Malformed signed Server-peer claim response")
        jobs = reply.get("jobs") or []
        if not isinstance(jobs, list) or len(jobs) > MAX_JOBS_PER_CLAIM:
            raise ServerPeerDenied("Server-peer job batch rejected")
        for job in jobs:
            if not isinstance(job, dict):
                raise ServerPeerDenied("Malformed Server-peer job")
            job_id = str(job.get("id") or "")
            claim = str(job.get("claim_token") or "")
            attempt = str(job.get("attempt_id") or "")
            if not job_id or not claim or not attempt:
                # No guessed acknowledgements. A missing token is not proof
                # that we own the claimed work.
                raise ServerPeerDenied("Missing signed job claim binding")
            result = execute_peer_job(job)
            # A completion failure MUST NOT cause re-execution of a write. The
            # existing server job queue retains bounded at-most-one claim
            # semantics and its deadline/recovery state.
            management.complete_ai_job_on_server(
                root=self.root, job_id=job_id, result=result,
                claim_token=claim, attempt_id=attempt,
            )
        return len(jobs)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                count = self.run_once()
                sleep = 0.2 if count else LOCAL_POLL_SECONDS
            except (ServerPeerDenied, management.MgmtSyncError, OSError, ValueError) as exc:
                # Do not print secrets, enrollment tokens, request bodies or
                # private key paths in the journald service logs.
                print("SERVER_PEER_UNAVAILABLE="+type(exc).__name__, file=sys.stderr)
                sleep = LOCAL_BACKOFF_SECONDS
            self.stop_event.wait(sleep)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DRLink Server peer MCP worker")
    parser.add_argument("--root", required=True, help="isolated enrolled Server-peer state")
    parser.add_argument("--check", action="store_true", help="read-only identity validation")
    parser.add_argument("--probe-central", action="store_true",
                        help="authenticated read-only central DRLink catalog probe")
    options = parser.parse_args(argv)
    try:
        validated = validate_peer_root(options.root)
    except ServerPeerDenied as exc:
        print("SERVER_PEER_STATE=DENY: "+str(exc), file=sys.stderr)
        return 2
    if options.check or options.probe_central:
        print("SERVER_PEER_STATE=VALID")
        print("SERVER_PEER_CENTRAL="+validated["central_origin"])
        if options.probe_central:
            try:
                data = management._request_json(
                    "GET", validated["central_origin"] + "/v1/catalog",
                    root=str(options.root),
                )
                if not isinstance(data, dict):
                    raise ServerPeerDenied("Central management catalog response is malformed")
            except (management.MgmtSyncError, OSError, ServerPeerDenied):
                print("SERVER_PEER_CENTRAL_AUTH=DENY", file=sys.stderr)
                return 2
            print("SERVER_PEER_CENTRAL_AUTH=PASS")
        return 0
    if os.environ.get("DRLINK_SERVER_PEER_ENABLED") != "1":
        print("SERVER_PEER_STATE=DISABLED", file=sys.stderr)
        return 2
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())
    signal.signal(signal.SIGINT, lambda signum, frame: stop.set())
    ServerPeerLoop(options.root, stop_event=stop).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
