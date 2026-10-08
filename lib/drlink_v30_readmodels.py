#!/usr/bin/env python3
"""Rebuildable Data Relay Link 3.0 operational read models.

These summaries are projections only. They never become configuration, recovery,
or enforcement authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from drlink_v30_jobs import job_operational_summary

READ_MODEL_SCHEMA_VERSION = 1
AGENT_HEARTBEAT_SECONDS = 120


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def overview_summary(conn, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    stale_before = _utc_text(current - timedelta(seconds=AGENT_HEARTBEAT_SECONDS))

    host = conn.execute(
        "SELECT COUNT(*) AS total,"
        "SUM(CASE WHEN agent_lifecycle_state='legacy' THEN 1 "
        "WHEN agent_lifecycle_state='connected' AND connected=1 "
        "AND agent_heartbeat_at IS NOT NULL AND agent_heartbeat_at>=? THEN 1 ELSE 0 END) "
        "AS connected,"
        "SUM(CASE WHEN agent_lifecycle_state='connected' AND connected=1 "
        "AND (agent_heartbeat_at IS NULL OR agent_heartbeat_at<?) THEN 1 ELSE 0 END) AS stale,"
        "SUM(CASE WHEN agent_lifecycle_state='disconnected' OR "
        "(agent_lifecycle_state<>'legacy' AND connected=0) THEN 1 ELSE 0 END) "
        "AS disconnected,"
        "SUM(CASE WHEN agent_lifecycle_state='legacy' THEN 1 ELSE 0 END) AS legacy,"
        "SUM(CASE WHEN agent_version IS NULL OR agent_version='' THEN 1 ELSE 0 END) "
        "AS version_unknown,"
        "SUM(CASE WHEN admission_state='PENDING_APPROVAL' THEN 1 ELSE 0 END) AS pending_approval,"
        "SUM(CASE WHEN admission_state='QUARANTINED' THEN 1 ELSE 0 END) AS quarantined,"
        "SUM(CASE WHEN admission_state='APPROVED' THEN 1 ELSE 0 END) AS approved "
        "FROM clients",
        (stale_before, stale_before),
    ).fetchone()

    service = conn.execute(
        "SELECT COUNT(*) AS total,"
        "SUM(CASE WHEN enabled=1 AND released=0 THEN 1 ELSE 0 END) AS enabled,"
        "SUM(CASE WHEN enabled=0 AND released=0 THEN 1 ELSE 0 END) AS disabled,"
        "SUM(CASE WHEN released=1 THEN 1 ELSE 0 END) AS released "
        "FROM published_services"
    ).fetchone()

    policy_rows = conn.execute(
        "SELECT plane,COUNT(*) AS total,"
        "SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) AS enabled "
        "FROM policy_rules GROUP BY plane ORDER BY plane"
    ).fetchall()
    policies = {
        str(row["plane"]): {
            "total": int(row["total"] or 0),
            "enabled": int(row["enabled"] or 0),
        }
        for row in policy_rows
    }
    ai_policy = conn.execute(
        "SELECT COUNT(*) AS total,"
        "SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) AS enabled "
        "FROM ai_policy_rules"
    ).fetchone()
    policies["ai"] = {
        "total": int(ai_policy["total"] or 0),
        "enabled": int(ai_policy["enabled"] or 0),
    }

    version_rows = conn.execute(
        "SELECT COALESCE(NULLIF(agent_platform,''),'unknown') AS platform,"
        "COALESCE(NULLIF(agent_version,''),'unknown') AS version,"
        "COUNT(*) AS hosts FROM clients "
        "GROUP BY COALESCE(NULLIF(agent_platform,''),'unknown'),"
        "COALESCE(NULLIF(agent_version,''),'unknown') "
        "ORDER BY hosts DESC,platform,version LIMIT 100"
    ).fetchall()

    return {
        "schema_version": READ_MODEL_SCHEMA_VERSION,
        "state_class": "DERIVED",
        "authoritative": False,
        "rebuildable": True,
        "generated_at": _utc_text(current),
        "managed_hosts": {
            "total": int(host["total"] or 0),
            "connected": int(host["connected"] or 0),
            "stale": int(host["stale"] or 0),
            "disconnected": int(host["disconnected"] or 0),
            "legacy": int(host["legacy"] or 0),
            "version_unknown": int(host["version_unknown"] or 0),
            "pending_approval": int(host["pending_approval"] or 0),
            "quarantined": int(host["quarantined"] or 0),
            "approved": int(host["approved"] or 0),
        },
        "remote_services": {
            "total": int(service["total"] or 0),
            "enabled": int(service["enabled"] or 0),
            "disabled": int(service["disabled"] or 0),
            "released": int(service["released"] or 0),
        },
        "policies": policies,
        "agent_versions": [
            {
                "platform": str(row["platform"]),
                "version": str(row["version"]),
                "hosts": int(row["hosts"] or 0),
            }
            for row in version_rows
        ],
        "management_jobs": job_operational_summary(conn),
    }
