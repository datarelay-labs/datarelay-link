#!/usr/bin/env python3
"""Data Relay Link 3.0 temporal authorization primitives."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)

PERMANENT = "PERMANENT"
ACTIVE = "ACTIVE"
EXPIRED = "EXPIRED"
CLOCK_UNTRUSTED = "CLOCK_UNTRUSTED"


@dataclass(frozen=True)
class TemporaryAccessState:
    status: str
    expires_at: Optional[str]
    now: str
    reason: str

    @property
    def allows_new_authorization(self) -> bool:
        return self.status in (PERMANENT, ACTIVE)


def _parse_utc(value: str, *, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is empty" % field)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("%s must be ISO-8601 with timezone" % field) from exc
    if dt.tzinfo is None:
        raise ValueError("%s must include timezone" % field)
    return dt.astimezone(timezone.utc)


def canonical_expiry(value: str) -> str:
    dt = _parse_utc(value, field="expires_at")
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def temporary_access_state(
    expires_at: Optional[str],
    *,
    created_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> TemporaryAccessState:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include timezone")
    current = current.astimezone(timezone.utc)
    current_s = current.isoformat(timespec="seconds").replace("+00:00", "Z")

    if not expires_at:
        return TemporaryAccessState(PERMANENT, None, current_s, "no expiry configured")

    try:
        expiry = _parse_utc(str(expires_at), field="expires_at")
    except ValueError:
        return TemporaryAccessState(
            CLOCK_UNTRUSTED,
            str(expires_at),
            current_s,
            "invalid expiry timestamp; fail closed",
        )

    if created_at:
        try:
            created = _parse_utc(str(created_at), field="created_at")
        except ValueError:
            return TemporaryAccessState(
                CLOCK_UNTRUSTED,
                canonical_expiry(str(expires_at)),
                current_s,
                "invalid rule creation timestamp; fail closed",
            )
        if current + CLOCK_SKEW_TOLERANCE < created:
            return TemporaryAccessState(
                CLOCK_UNTRUSTED,
                canonical_expiry(str(expires_at)),
                current_s,
                "server clock moved materially before rule creation time; fail closed",
            )

    expiry_s = expiry.isoformat(timespec="seconds").replace("+00:00", "Z")
    if current >= expiry:
        return TemporaryAccessState(EXPIRED, expiry_s, current_s, "temporary access expired")
    return TemporaryAccessState(ACTIVE, expiry_s, current_s, "temporary access is active")


def expiry_allows_new_authorization(
    expires_at: Optional[str],
    *,
    created_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    return temporary_access_state(expires_at, created_at=created_at, now=now).allows_new_authorization


def rule_effective_for_new_authorization(
    *,
    policy_mode: Optional[str],
    expires_at: Optional[str],
    created_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Return whether a rule participates in a new authorization decision.

    Temporary Access is a grant-expiry feature. It is supported only for
    WHITELIST rules. If an expiry somehow appears on a BLACKLIST rule, do not
    let time disable that blocking rule: keeping it effective is the
    fail-closed behavior until the invalid state is repaired.
    """
    if not expires_at:
        return True
    if str(policy_mode or "").strip().lower() != "whitelist":
        return True
    return expiry_allows_new_authorization(
        expires_at,
        created_at=created_at,
        now=now,
    )


def row_effective_for_new_authorization(
    row,
    *,
    policy_mode: Optional[str],
    now: Optional[datetime] = None,
) -> bool:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    expires_at = row["expires_at"] if "expires_at" in keys else None
    created_at = row["created_at"] if "created_at" in keys else None
    return rule_effective_for_new_authorization(
        policy_mode=policy_mode,
        expires_at=expires_at,
        created_at=created_at,
        now=now,
    )
