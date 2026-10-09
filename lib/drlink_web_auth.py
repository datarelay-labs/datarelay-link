#!/usr/bin/env python3
"""Core-owned local Web operator, MFA, and browser-session security."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from drlink_control_db import ControlPlaneError, open_control_db, utc_now_iso
from drlink_management_catalog import MANAGEMENT_PERMISSION_NAMES
from frp_mgmt_auth import decrypt_token_pbkdf2, encrypt_token_pbkdf2
from drlink_foundation_security import (
    foundation_new_totp_secret,
    foundation_totp_code_at,
    foundation_verify_totp,
)

ROLE_ADMIN = "Admin"
ROLE_OPERATOR = "Operator"
ROLE_READ_ONLY = "Read Only"
WEB_ROLES = frozenset({ROLE_ADMIN, ROLE_OPERATOR, ROLE_READ_ONLY})

SESSION_LIFETIME_SECONDS = 8 * 60 * 60
SESSION_IDLE_SECONDS = 30 * 60
SESSION_REFRESH_SECONDS = 60
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_MAX_FAILURES = 5
LOGIN_BUCKET_LIMIT = 1024
PASSWORD_PBKDF2_ITERATIONS = 600000
PASSWORD_KDF = "pbkdf2-hmac-sha256-i600000"
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
RECOVERY_CODE_COUNT = 10
MFA_ENROLLMENT_SECONDS = 10 * 60
MFA_ENROLLMENT_LIMIT = 1024
MFA_LOGIN_CHALLENGE_SECONDS = 3 * 60
MFA_LOGIN_CHALLENGE_LIMIT = 1024

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_READ_PERMISSIONS = frozenset(
    {
        "management-read",
        "management-diagnose",
        "management-policy-test",
        "management-job-observe",
    }
)
_OPERATOR_PERMISSIONS = _READ_PERMISSIONS | frozenset(
    {
        "management-temporary-access",
        "management-config",
        "management-job-run",
    }
)
_ADMIN_PERMISSIONS = frozenset(MANAGEMENT_PERMISSION_NAMES)


@dataclass(frozen=True)
class WebPrincipal:
    operator_id: str
    username: str
    role: str
    permissions: frozenset[str]
    session_id: str


@dataclass(frozen=True)
class WebSessionIssue:
    session_id: str
    session_token: str
    csrf_token: str
    expires_at: str
    idle_expires_at: str
    principal: WebPrincipal


@dataclass(frozen=True)
class WebMfaEnrollmentChallenge:
    enrollment_token: str
    totp_secret: str
    otpauth_uri: str
    expires_at: str
    operator_id: str
    username: str
    role: str


@dataclass(frozen=True)
class WebMfaLoginChallenge:
    """Pre-authentication only. Never grants a principal, cookie or role."""
    challenge_token: str
    expires_at: str


def permissions_for_role(role: str) -> frozenset[str]:
    name = str(role or "").strip()
    if name == ROLE_ADMIN:
        return _ADMIN_PERMISSIONS
    if name == ROLE_OPERATOR:
        return _OPERATOR_PERMISSIONS
    if name == ROLE_READ_ONLY:
        return _READ_PERMISSIONS
    raise ControlPlaneError("Unsupported Web operator role.")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _password_hash(password: str, salt: bytes) -> str:
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt,
        PASSWORD_PBKDF2_ITERATIONS,
        dklen=32,
    )
    return base64.b64encode(raw).decode("ascii")


def _validate_password(password: str) -> str:
    value = str(password or "")
    if len(value) < 8:
        raise ControlPlaneError("Web operator password must be at least 8 characters.")
    if len(value) > 1024:
        raise ControlPlaneError("Web operator password is too long.")
    if not re.search(r"[A-Z]", value):
        raise ControlPlaneError("Web operator password must include an uppercase letter.")
    if not re.search(r"[a-z]", value):
        raise ControlPlaneError("Web operator password must include a lowercase letter.")
    if not re.search(r"[0-9]", value):
        raise ControlPlaneError("Web operator password must include a digit.")
    return value


def _validate_username(username: str) -> str:
    value = str(username or "").strip()
    if not _USERNAME_RE.fullmatch(value):
        raise ControlPlaneError(
            "Web operator username must start with a letter and use letters, digits, '.', '_' or '-'."
        )
    return value


def _master_key_path(root: Optional[str] = None) -> Path:
    if root and str(root) not in ("", "/"):
        return Path(root) / "var/lib/drlink/web-auth.key"
    return Path("/var/lib/drlink/web-auth.key")


def _master_key(root: Optional[str] = None, *, create: bool = True) -> bytes:
    path = _master_key_path(root)
    try:
        raw = path.read_text(encoding="ascii").strip()
        key = base64.b64decode(raw.encode("ascii"), validate=True)
        if len(key) != 32:
            raise ValueError("invalid key length")
        return key
    except FileNotFoundError:
        if not create:
            raise ControlPlaneError("Web protected-credential key is unavailable.")
    except Exception as exc:
        raise ControlPlaneError("Web protected-credential key is invalid.") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    tmp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, base64.b64encode(key) + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(str(tmp), str(path))
    except FileExistsError:
        pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    os.chmod(path, 0o600)
    return _master_key(root, create=False)


def generate_totp_secret() -> str:
    """The same 160-bit RFC6238 seed generator as other DataRelay products."""
    return foundation_new_totp_secret()


def totp_code(secret: str, *, at: Optional[datetime] = None) -> tuple[str, int]:
    """Keep the native (code, counter) contract using Foundation TOTP."""
    current = at or _utc_now()
    counter = int(current.timestamp()) // TOTP_STEP_SECONDS
    return foundation_totp_code_at(secret, current.timestamp()), counter


def verify_totp(
    secret: str,
    supplied: str,
    *,
    at: Optional[datetime] = None,
    last_counter: Optional[int] = None,
) -> Optional[int]:
    """Reuse Foundation OTP replay-window semantics; Core owns SQLite CAS."""
    code = str(supplied or "").strip()
    if len(code) != TOTP_DIGITS or not code.isascii() or not code.isdigit():
        return None
    current = at or _utc_now()
    return foundation_verify_totp(
        secret, code, now=current.timestamp(), last_counter=last_counter,
    )


def generate_recovery_codes() -> list[str]:
    out: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
        out.append("-".join(raw[i : i + 4] for i in range(0, 16, 4)))
    return out


def _recovery_hash(master: bytes, code: str) -> str:
    normalized = str(code or "").strip().upper().replace(" ", "")
    return hmac.new(master, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _user_agent_hash(value: str) -> str:
    return _sha256_text(str(value or "")[:1024])


class WebAuthService:
    def __init__(self, root: Optional[str] = None):
        self.root = root
        self.conn = open_control_db(root)
        self._lock = threading.RLock()
        self._failures: dict[str, list[float]] = {}
        self._mfa_enrollments: dict[str, dict[str, Any]] = {}
        self._mfa_logins: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "WebAuthService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _audit(
        self,
        event_type: str,
        *,
        actor_id: str = "",
        result: str = "success",
        resource_id: str = "",
        reason_code: str = "",
    ) -> None:
        revision_row = self.conn.execute(
            "SELECT MAX(revision) FROM config_revisions"
        ).fetchone()
        revision = int(revision_row[0] or 0) if revision_row else 0
        revision_fk = revision if revision > 0 else None
        now = utc_now_iso()
        self.conn.execute(
            "INSERT INTO audit_events("
            "timestamp,revision,actor,action,entity_type,entity_id,operation,"
            "before_summary,after_summary,impact_summary,result,event_id,"
            "schema_version,category,event_type,occurred_at,source,actor_type,"
            "actor_id,interface,reason_code,revision_after,"
            "matched_policy_json,source_meta_json,destination_meta_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                now,
                revision_fk,
                actor_id or "web-local",
                event_type,
                "web-operator",
                resource_id,
                event_type,
                "",
                "",
                "",
                result,
                "evt_web_" + secrets.token_hex(16),
                1,
                "SECURITY_LIFECYCLE",
                event_type,
                now,
                "drlink-web",
                "web-operator",
                actor_id,
                "WEB",
                reason_code,
                revision,
                "[]",
                "{}",
                "{}",
            ),
        )

    def has_operator(self) -> bool:
        row = self.conn.execute("SELECT COUNT(*) FROM web_operators").fetchone()
        return bool(row and int(row[0] or 0))

    def prepare_mfa_material(self, username: str) -> dict[str, Any]:
        name = _validate_username(username)
        secret = generate_totp_secret()
        codes = generate_recovery_codes()
        label = quote("Data Relay Link:%s" % name, safe="")
        issuer = quote("Data Relay Link", safe="")
        uri = "otpauth://totp/%s?secret=%s&issuer=%s&digits=%d&period=%d" % (
            label,
            secret,
            issuer,
            TOTP_DIGITS,
            TOTP_STEP_SECONDS,
        )
        return {"totp_secret": secret, "otpauth_uri": uri, "recovery_codes": codes}

    def create_first_admin(
        self,
        *,
        username: str,
        password: str,
        totp_secret: str = "",
        recovery_codes: Optional[list[str]] = None,
        totp_value: str = "",
        mfa_required: bool = False,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Create the first local Admin. MFA is off unless explicitly supplied/enabled."""
        name = _validate_username(username)
        password_value = _validate_password(password)
        current = now or _utc_now()
        require_mfa = bool(mfa_required or str(totp_secret or "").strip())
        codes = list(recovery_codes or [])
        counter: Optional[int] = None
        cipher = ""
        code_hashes: list[str] = []
        if require_mfa:
            counter = verify_totp(totp_secret, totp_value, at=current)
            if counter is None:
                raise ControlPlaneError("TOTP verification failed.")
            if len(codes) < 5:
                raise ControlPlaneError("Recovery code set is incomplete.")
            master = _master_key(self.root)
            cipher = encrypt_token_pbkdf2(totp_secret, master)
            code_hashes = sorted({_recovery_hash(master, code) for code in codes})
        salt = os.urandom(16)
        operator_id = "wop_" + secrets.token_hex(12)
        created = _utc_text(current)
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                if int(self.conn.execute("SELECT COUNT(*) FROM web_operators").fetchone()[0]):
                    raise ControlPlaneError(
                        "First Web Admin already exists; use local recovery/admin management."
                    )
                self.conn.execute(
                    "INSERT INTO web_operators("
                    "id,username,role,enabled,recovery_admin,password_salt,password_hash,"
                    "password_kdf,mfa_secret_ciphertext,mfa_required,mfa_enrolled,mfa_last_counter,"
                    "created_at,updated_at"
                    ") VALUES (?,?,?,1,1,?,?,?,?,?,?,?, ?,?)",
                    (
                        operator_id,
                        name,
                        ROLE_ADMIN,
                        base64.b64encode(salt).decode("ascii"),
                        _password_hash(password_value, salt),
                        PASSWORD_KDF,
                        cipher,
                        1 if require_mfa else 0,
                        1 if require_mfa else 0,
                        counter,
                        created,
                        created,
                    ),
                )
                if code_hashes:
                    self.conn.executemany(
                        "INSERT INTO web_recovery_codes(operator_id,code_hash,created_at) "
                        "VALUES (?,?,?)",
                        [(operator_id, digest, created) for digest in code_hashes],
                    )
                self._audit(
                    "web.operator.bootstrap",
                    actor_id=operator_id,
                    resource_id=operator_id,
                    reason_code="MFA_ON" if require_mfa else "MFA_OFF_DEFAULT",
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return {
            "operator_id": operator_id,
            "username": name,
            "role": ROLE_ADMIN,
            "mfa_required": require_mfa,
            "mfa_enrolled": require_mfa,
            "recovery_admin": True,
        }

    def create_operator_local(
        self,
        *,
        username: str,
        role: str,
        password: str,
        totp_secret: str = "",
        recovery_codes: Optional[list[str]] = None,
        totp_value: str = "",
        mfa_required: bool = False,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Create an additional local Web operator; MFA defaults to disabled."""
        name = _validate_username(username)
        role_name = str(role or "").strip()
        if role_name not in WEB_ROLES:
            raise ControlPlaneError("Unsupported Web operator role.")
        password_value = _validate_password(password)
        current = now or _utc_now()
        require_mfa = bool(mfa_required or str(totp_secret or "").strip())
        codes = list(recovery_codes or [])
        counter: Optional[int] = None
        cipher = ""
        code_hashes: list[str] = []
        if require_mfa:
            counter = verify_totp(totp_secret, totp_value, at=current)
            if counter is None:
                raise ControlPlaneError("TOTP verification failed.")
            if len(codes) < 5:
                raise ControlPlaneError("Recovery code set is incomplete.")
            master = _master_key(self.root)
            cipher = encrypt_token_pbkdf2(totp_secret, master)
            code_hashes = sorted({_recovery_hash(master, code) for code in codes})
        salt = os.urandom(16)
        operator_id = "wop_" + secrets.token_hex(12)
        created = _utc_text(current)
        with self._lock:
            recovery = self.conn.execute(
                "SELECT COUNT(*) FROM web_operators WHERE recovery_admin=1 AND enabled=1"
            ).fetchone()
            if not recovery or int(recovery[0] or 0) < 1:
                raise ControlPlaneError("A local recovery Admin must exist first.")
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "INSERT INTO web_operators("
                    "id,username,role,enabled,recovery_admin,password_salt,password_hash,"
                    "password_kdf,mfa_secret_ciphertext,mfa_required,mfa_enrolled,mfa_last_counter,"
                    "created_at,updated_at"
                    ") VALUES (?,?,?,1,0,?,?,?,?,?,?,?, ?,?)",
                    (
                        operator_id, name, role_name,
                        base64.b64encode(salt).decode("ascii"),
                        _password_hash(password_value, salt), PASSWORD_KDF, cipher,
                        1 if require_mfa else 0, 1 if require_mfa else 0,
                        counter, created, created,
                    ),
                )
                if code_hashes:
                    self.conn.executemany(
                        "INSERT INTO web_recovery_codes(operator_id,code_hash,created_at) VALUES (?,?,?)",
                        [(operator_id, digest, created) for digest in code_hashes],
                    )
                self._audit(
                    "web.operator.created",
                    actor_id="local-root",
                    resource_id=operator_id,
                    reason_code="MFA_ON" if require_mfa else "MFA_OFF_DEFAULT",
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return {
            "operator_id": operator_id,
            "username": name,
            "role": role_name,
            "mfa_required": require_mfa,
            "mfa_enrolled": require_mfa,
        }

    def list_operators(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id,username,role,enabled,recovery_admin,mfa_required,mfa_enrolled,"
            "created_at,updated_at,last_login_at FROM web_operators "
            "ORDER BY username COLLATE NOCASE,id"
        ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "username": str(row["username"]),
                "role": str(row["role"]),
                "enabled": bool(row["enabled"]),
                "recovery_admin": bool(row["recovery_admin"]),
                "mfa_required": bool(row["mfa_required"]),
                "mfa_enrolled": bool(row["mfa_enrolled"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_login_at": row["last_login_at"],
            }
            for row in rows
        ]

    def _drop_mfa_challenges(self, operator_id: str) -> None:
        for bucket in (self._mfa_enrollments, self._mfa_logins):
            stale = [
                key for key, item in bucket.items()
                if str(item.get("operator_id") or "") == str(operator_id)
            ]
            for key in stale:
                bucket.pop(key, None)

    def set_operator_mfa_required(
        self, operator_id: str, *, required: bool, actor_id: str
    ) -> dict[str, Any]:
        ident = str(operator_id or "").strip()
        with self._lock:
            row = self.conn.execute(
                "SELECT id,username,mfa_required FROM web_operators WHERE id=?", (ident,)
            ).fetchone()
            if not row:
                raise ControlPlaneError("Web operator was not found.")
            target = 1 if bool(required) else 0
            changed = int(row["mfa_required"] or 0) != target
            now = utc_now_iso()
            revoked = 0
            if changed:
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    self.conn.execute(
                        "UPDATE web_operators SET mfa_required=?,mfa_enrolled=0,"
                        "mfa_secret_ciphertext='',mfa_last_counter=NULL,"
                        "row_version=row_version+1,updated_at=? WHERE id=?",
                        (target, now, ident),
                    )
                    self.conn.execute(
                        "DELETE FROM web_recovery_codes WHERE operator_id=?", (ident,)
                    )
                    revoked = self.conn.execute(
                        "UPDATE web_sessions SET revoked_at=? "
                        "WHERE operator_id=? AND revoked_at IS NULL",
                        (now, ident),
                    ).rowcount
                    self._audit(
                        "web.operator.mfa.enabled" if target else "web.operator.mfa.disabled",
                        actor_id=str(actor_id or ""),
                        resource_id=ident,
                        reason_code="ADMIN_MFA_POLICY_CHANGE",
                    )
                    self.conn.execute("COMMIT")
                except Exception:
                    try:
                        self.conn.execute("ROLLBACK")
                    except Exception:
                        pass
                    raise
                self._drop_mfa_challenges(ident)
            return {
                "operator_id": ident,
                "username": str(row["username"]),
                "mfa_required": bool(target),
                "mfa_enrolled": False if changed else bool(
                    self.conn.execute(
                        "SELECT mfa_enrolled FROM web_operators WHERE id=?", (ident,)
                    ).fetchone()[0]
                ),
                "sessions_revoked": int(revoked),
                "changed": changed,
            }

    def _failure_key(self, username: str, source_addr: str) -> str:
        return _sha256_text("%s\n%s" % (str(username).lower(), str(source_addr)))[:32]

    def _rate_limited(self, key: str, now_mono: float) -> bool:
        cutoff = now_mono - LOGIN_WINDOW_SECONDS
        entries = [value for value in self._failures.get(key, []) if value >= cutoff]
        self._failures[key] = entries
        return len(entries) >= LOGIN_MAX_FAILURES

    def _note_failure(self, key: str, now_mono: float) -> None:
        if len(self._failures) >= LOGIN_BUCKET_LIMIT and key not in self._failures:
            oldest = min(
                self._failures,
                key=lambda item: self._failures[item][0]
                if self._failures[item]
                else float("-inf"),
            )
            self._failures.pop(oldest, None)
        self._failures.setdefault(key, []).append(now_mono)

    def _begin_mfa_enrollment(
        self, row, *, current: datetime
    ) -> WebMfaEnrollmentChallenge:
        now_mono = time.monotonic()
        for key, item in list(self._mfa_enrollments.items()):
            if float(item.get("expires_mono") or 0) <= now_mono:
                self._mfa_enrollments.pop(key, None)
        if len(self._mfa_enrollments) >= MFA_ENROLLMENT_LIMIT:
            oldest = min(
                self._mfa_enrollments,
                key=lambda key: float(self._mfa_enrollments[key].get("created_mono") or 0),
            )
            self._mfa_enrollments.pop(oldest, None)
        self._drop_mfa_challenges(str(row["id"]))
        token = secrets.token_urlsafe(32)
        token_hash = _sha256_text(token)
        secret = generate_totp_secret()
        expires_dt = current + timedelta(seconds=MFA_ENROLLMENT_SECONDS)
        label = quote("Data Relay Link:%s" % str(row["username"]), safe="")
        issuer = quote("Data Relay Link", safe="")
        uri = "otpauth://totp/%s?secret=%s&issuer=%s&digits=%d&period=%d" % (
            label, secret, issuer, TOTP_DIGITS, TOTP_STEP_SECONDS
        )
        self._mfa_enrollments[token_hash] = {
            "operator_id": str(row["id"]),
            "secret": secret,
            "created_mono": now_mono,
            "expires_mono": now_mono + MFA_ENROLLMENT_SECONDS,
            "attempts": 0,
        }
        self._audit(
            "web.operator.mfa.enrollment.started",
            actor_id=str(row["id"]),
            resource_id=str(row["id"]),
        )
        return WebMfaEnrollmentChallenge(
            enrollment_token=token,
            totp_secret=secret,
            otpauth_uri=uri,
            expires_at=_utc_text(expires_dt),
            operator_id=str(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
        )

    def _issue_session(
        self,
        row,
        *,
        current: datetime,
        source_addr: str,
        user_agent: str,
        new_counter: Optional[int] = None,
        consumed_hash: Optional[str] = None,
    ) -> WebSessionIssue:
        operator_id = str(row["id"])
        session_id = "ws_" + secrets.token_hex(12)
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        created = _utc_text(current)
        expires_dt = current + timedelta(seconds=SESSION_LIFETIME_SECONDS)
        idle_dt = min(expires_dt, current + timedelta(seconds=SESSION_IDLE_SECONDS))
        expires = _utc_text(expires_dt)
        idle = _utc_text(idle_dt)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            # Check current operator identity inside the very transaction
            # that consumes OTP/recovery and mints the authenticated session.
            # A second process may change the user's role/MFA/password state
            # between the password and factor stages.
            fresh = self.conn.execute(
                "SELECT enabled,role,row_version,mfa_required,mfa_enrolled "
                "FROM web_operators WHERE id=?", (operator_id,),
            ).fetchone()
            if (
                not fresh or not int(fresh["enabled"] or 0)
                or str(fresh["role"]) != str(row["role"])
                or int(fresh["row_version"] or 0) != int(row["row_version"] or 0)
                or (int(row["mfa_required"] or 0) and not (
                    int(fresh["mfa_required"] or 0)
                    and int(fresh["mfa_enrolled"] or 0)
                ))
            ):
                raise ControlPlaneError("Invalid credentials or MFA.")
            if consumed_hash:
                changed = self.conn.execute(
                    "UPDATE web_recovery_codes SET consumed_at=? "
                    "WHERE operator_id=? AND code_hash=? AND consumed_at IS NULL",
                    (created, operator_id, consumed_hash),
                ).rowcount
                if changed != 1:
                    raise ControlPlaneError("Invalid credentials or MFA.")
            if new_counter is not None:
                changed = self.conn.execute(
                    "UPDATE web_operators SET mfa_last_counter=?,last_login_at=?,"
                    "updated_at=? WHERE id=? AND "
                    "(mfa_last_counter IS NULL OR mfa_last_counter<?)",
                    (new_counter, created, created, operator_id, new_counter),
                ).rowcount
                if changed != 1:
                    raise ControlPlaneError("Invalid credentials or MFA.")
            else:
                self.conn.execute(
                    "UPDATE web_operators SET last_login_at=?,updated_at=? WHERE id=?",
                    (created, created, operator_id),
                )
            self.conn.execute(
                "INSERT INTO web_sessions("
                "id,operator_id,token_hash,csrf_hash,created_at,last_seen_at,"
                "expires_at,idle_expires_at,source_addr,user_agent_hash"
                ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id, operator_id, _sha256_text(token), _sha256_text(csrf),
                    created, created, expires, idle, str(source_addr or "")[:128],
                    _user_agent_hash(user_agent),
                ),
            )
            self._audit(
                "web.login.succeeded", actor_id=operator_id, resource_id=session_id
            )
            self.conn.execute("COMMIT")
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        principal = WebPrincipal(
            operator_id=operator_id,
            username=str(row["username"]),
            role=str(row["role"]),
            permissions=permissions_for_role(str(row["role"])),
            session_id=session_id,
        )
        return WebSessionIssue(
            session_id=session_id,
            session_token=token,
            csrf_token=csrf,
            expires_at=expires,
            idle_expires_at=idle,
            principal=principal,
        )

    def begin_password_login(
        self,
        *,
        username: str,
        password: str,
        source_addr: str = "",
        user_agent: str = "",
        now: Optional[datetime] = None,
    ) -> WebSessionIssue | WebMfaEnrollmentChallenge | WebMfaLoginChallenge:
        """Password stage. No session exists for enrolled MFA users until OTP."""
        current = now or _utc_now()
        now_mono = time.monotonic()
        key = self._failure_key(username, source_addr)
        with self._lock:
            if self._rate_limited(key, now_mono):
                self._audit("web.login.failed", result="deny", reason_code="RATE_LIMITED")
                raise ControlPlaneError("Invalid credentials or MFA.")
            row = self.conn.execute(
                "SELECT * FROM web_operators WHERE username=? COLLATE NOCASE",
                (str(username or "").strip(),),
            ).fetchone()
            # Preserve the existing constant-cost missing-user password check.
            salt = b"\x00" * 16
            expected = _password_hash("not-the-password", salt)
            if row:
                try:
                    salt = base64.b64decode(str(row["password_salt"]).encode("ascii"))
                    expected = str(row["password_hash"])
                except Exception:
                    pass
            actual = _password_hash(str(password or ""), salt)
            if not row or not int(row["enabled"] or 0) or not hmac.compare_digest(actual, expected):
                self._note_failure(key, now_mono)
                self._audit("web.login.failed", result="deny", reason_code="INVALID_AUTH")
                raise ControlPlaneError("Invalid credentials or MFA.")
            if not bool(int(row["mfa_required"] or 0)):
                self._failures.pop(key, None)
                return self._issue_session(
                    row, current=current, source_addr=source_addr, user_agent=user_agent,
                )
            if not bool(int(row["mfa_enrolled"] or 0)):
                self._failures.pop(key, None)
                return self._begin_mfa_enrollment(row, current=current)
            # MFA is not authenticated yet. Preserve failed OTP counters
            # across repeated password-first challenges until the second
            # factor succeeds, or the login throttle can be bypassed.

            # Hash and bound short-lived pre-auth challenges; no password,
            # bearer session or TOTP seed is retained in this entry.
            for token_hash, value in list(self._mfa_logins.items()):
                if float(value["expires_mono"]) <= now_mono:
                    self._mfa_logins.pop(token_hash, None)
            if len(self._mfa_logins) >= MFA_LOGIN_CHALLENGE_LIMIT:
                oldest = min(self._mfa_logins, key=lambda h: self._mfa_logins[h]["created_mono"])
                self._mfa_logins.pop(oldest, None)
            token = secrets.token_urlsafe(32)
            token_hash = _sha256_text(token)
            self._mfa_logins[token_hash] = {
                "operator_id": str(row["id"]),
                "row_version": int(row["row_version"] or 0),
                "role": str(row["role"]),
                "source_hash": _sha256_text(str(source_addr or "")[:128]),
                "agent_hash": _user_agent_hash(user_agent),
                "created_mono": now_mono,
                "expires_mono": now_mono + MFA_LOGIN_CHALLENGE_SECONDS,
            }
            self._audit(
                "web.login.mfa.pending", actor_id=str(row["id"]),
                resource_id=str(row["id"]),
            )
            return WebMfaLoginChallenge(
                challenge_token=token,
                expires_at=_utc_text(current + timedelta(seconds=MFA_LOGIN_CHALLENGE_SECONDS)),
            )

    def complete_password_login(
        self,
        *,
        challenge_token: str,
        totp_value: str = "",
        recovery_code: str = "",
        source_addr: str = "",
        user_agent: str = "",
        now: Optional[datetime] = None,
    ) -> WebSessionIssue:
        """Single-use source-bound OTP stage. Recheck live SQLite authority."""
        current = now or _utc_now()
        now_mono = time.monotonic()
        token_hash = _sha256_text(str(challenge_token or ""))
        with self._lock:
            item = self._mfa_logins.pop(token_hash, None)
            if not item or float(item["expires_mono"]) <= now_mono:
                raise ControlPlaneError("Invalid credentials or MFA.")
            if not (
                hmac.compare_digest(item["source_hash"], _sha256_text(str(source_addr or "")[:128]))
                and hmac.compare_digest(item["agent_hash"], _user_agent_hash(user_agent))
            ):
                raise ControlPlaneError("Invalid credentials or MFA.")
            operator_id = str(item["operator_id"])
            row = self.conn.execute(
                "SELECT * FROM web_operators WHERE id=?", (operator_id,),
            ).fetchone()
            if not row or not (
                int(row["enabled"] or 0)
                and int(row["mfa_required"] or 0)
                and int(row["mfa_enrolled"] or 0)
                and int(row["row_version"] or 0) == item["row_version"]
                and str(row["role"]) == item["role"]
            ):
                raise ControlPlaneError("Invalid credentials or MFA.")
            key = self._failure_key(str(row["username"]), source_addr)
            if self._rate_limited(key, now_mono):
                raise ControlPlaneError("Invalid credentials or MFA.")
            new_counter: Optional[int] = None
            consumed_hash: Optional[str] = None
            try:
                master = _master_key(self.root, create=False)
                if str(totp_value or "").strip():
                    secret = decrypt_token_pbkdf2(
                        str(row["mfa_secret_ciphertext"]), master,
                    )
                    new_counter = verify_totp(
                        secret, totp_value, at=current,
                        last_counter=row["mfa_last_counter"],
                    )
                    if new_counter is None:
                        raise ControlPlaneError("Invalid credentials or MFA.")
                elif str(recovery_code or "").strip():
                    consumed_hash = _recovery_hash(master, recovery_code)
                    recovery = self.conn.execute(
                        "SELECT consumed_at FROM web_recovery_codes "
                        "WHERE operator_id=? AND code_hash=?",
                        (operator_id, consumed_hash),
                    ).fetchone()
                    if not recovery or recovery["consumed_at"] is not None:
                        raise ControlPlaneError("Invalid credentials or MFA.")
                else:
                    raise ControlPlaneError("Invalid credentials or MFA.")
                # _issue_session transactionally consumes recovery codes and
                # uses a compare-and-swap TOTP counter to prevent replay.
                issued = self._issue_session(
                    row, current=current, source_addr=source_addr,
                    user_agent=user_agent, new_counter=new_counter,
                    consumed_hash=consumed_hash,
                )
            except Exception:
                self._note_failure(key, now_mono)
                self._audit(
                    "web.login.failed", actor_id=operator_id, resource_id=operator_id,
                    result="deny", reason_code="INVALID_MFA",
                )
                raise ControlPlaneError("Invalid credentials or MFA.") from None
            self._failures.pop(key, None)
            return issued

    def cancel_password_login(self, challenge_token: str) -> bool:
        """Discard a pending challenge without exposing a user or session."""
        with self._lock:
            return self._mfa_logins.pop(
                _sha256_text(str(challenge_token or "")), None
            ) is not None

    def authenticate(
        self,
        *,
        username: str,
        password: str,
        totp_value: str = "",
        recovery_code: str = "",
        source_addr: str = "",
        user_agent: str = "",
        now: Optional[datetime] = None,
    ) -> WebSessionIssue | WebMfaEnrollmentChallenge:
        current = now or _utc_now()
        now_mono = time.monotonic()
        key = self._failure_key(username, source_addr)
        with self._lock:
            if self._rate_limited(key, now_mono):
                self._audit("web.login.failed", result="deny", reason_code="RATE_LIMITED")
                raise ControlPlaneError("Invalid credentials or MFA.")
            row = self.conn.execute(
                "SELECT * FROM web_operators WHERE username=? COLLATE NOCASE",
                (str(username or "").strip(),),
            ).fetchone()
            dummy_salt = b"\x00" * 16
            salt = dummy_salt
            expected = _password_hash("not-the-password", dummy_salt)
            if row:
                try:
                    salt = base64.b64decode(str(row["password_salt"]).encode("ascii"))
                    expected = str(row["password_hash"])
                except Exception:
                    pass
            actual = _password_hash(str(password or ""), salt)
            password_ok = bool(row) and hmac.compare_digest(actual, expected)
            enabled = bool(row and int(row["enabled"] or 0))
            if not password_ok or not enabled:
                self._note_failure(key, now_mono)
                self._audit("web.login.failed", result="deny", reason_code="INVALID_AUTH")
                raise ControlPlaneError("Invalid credentials or MFA.")

            operator_id = str(row["id"])
            required = bool(int(row["mfa_required"] or 0))
            enrolled = bool(int(row["mfa_enrolled"] or 0))
            if required and not enrolled:
                self._failures.pop(key, None)
                return self._begin_mfa_enrollment(row, current=current)

            new_counter: Optional[int] = None
            consumed_hash: Optional[str] = None
            if required:
                master = _master_key(self.root, create=False)
                mfa_ok = False
                if str(totp_value or "").strip():
                    try:
                        secret = decrypt_token_pbkdf2(
                            str(row["mfa_secret_ciphertext"]), master
                        )
                        new_counter = verify_totp(
                            secret, totp_value, at=current,
                            last_counter=row["mfa_last_counter"],
                        )
                        mfa_ok = new_counter is not None
                    except Exception:
                        mfa_ok = False
                elif str(recovery_code or "").strip():
                    consumed_hash = _recovery_hash(master, recovery_code)
                    recovery = self.conn.execute(
                        "SELECT consumed_at FROM web_recovery_codes "
                        "WHERE operator_id=? AND code_hash=?",
                        (operator_id, consumed_hash),
                    ).fetchone()
                    mfa_ok = bool(recovery and recovery["consumed_at"] is None)
                if not mfa_ok:
                    self._note_failure(key, now_mono)
                    self._audit(
                        "web.login.failed", actor_id=operator_id, resource_id=operator_id,
                        result="deny", reason_code="INVALID_MFA",
                    )
                    raise ControlPlaneError("Invalid credentials or MFA.")

            self._failures.pop(key, None)
            return self._issue_session(
                row, current=current, source_addr=source_addr, user_agent=user_agent,
                new_counter=new_counter, consumed_hash=consumed_hash,
            )

    def cancel_mfa_enrollment(self, enrollment_token: str) -> bool:
        token_hash = _sha256_text(str(enrollment_token or "").strip())
        with self._lock:
            item = self._mfa_enrollments.pop(token_hash, None)
            if not item:
                return False
            operator_id = str(item.get("operator_id") or "")
            self._audit(
                "web.operator.mfa.enrollment.cancelled",
                actor_id=operator_id,
                resource_id=operator_id,
            )
            return True

    def confirm_mfa_enrollment(
        self,
        *,
        enrollment_token: str,
        totp_value: str,
        source_addr: str = "",
        user_agent: str = "",
        now: Optional[datetime] = None,
    ) -> tuple[WebSessionIssue, list[str]]:
        current = now or _utc_now()
        token_hash = _sha256_text(str(enrollment_token or "").strip())
        with self._lock:
            item = self._mfa_enrollments.get(token_hash)
            if not item or float(item.get("expires_mono") or 0) <= time.monotonic():
                self._mfa_enrollments.pop(token_hash, None)
                raise ControlPlaneError("MFA enrollment expired; sign in again.")
            operator_id = str(item.get("operator_id") or "")
            row = self.conn.execute(
                "SELECT * FROM web_operators WHERE id=?", (operator_id,)
            ).fetchone()
            if not row or not int(row["enabled"] or 0) or not int(row["mfa_required"] or 0):
                self._mfa_enrollments.pop(token_hash, None)
                raise ControlPlaneError("MFA enrollment is no longer required.")
            if int(row["mfa_enrolled"] or 0):
                self._mfa_enrollments.pop(token_hash, None)
                raise ControlPlaneError("MFA is already enrolled.")
            secret = str(item.get("secret") or "")
            counter = verify_totp(secret, totp_value, at=current)
            if counter is None:
                item["attempts"] = int(item.get("attempts") or 0) + 1
                if int(item["attempts"]) >= 5:
                    self._mfa_enrollments.pop(token_hash, None)
                raise ControlPlaneError("Invalid MFA enrollment code.")
            recovery_codes = generate_recovery_codes()
            master = _master_key(self.root)
            code_hashes = sorted({_recovery_hash(master, code) for code in recovery_codes})
            now_text = _utc_text(current)
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "UPDATE web_operators SET mfa_secret_ciphertext=?,mfa_enrolled=1,"
                    "mfa_last_counter=?,row_version=row_version+1,updated_at=? WHERE id=?",
                    (encrypt_token_pbkdf2(secret, master), counter, now_text, operator_id),
                )
                self.conn.execute(
                    "DELETE FROM web_recovery_codes WHERE operator_id=?", (operator_id,)
                )
                self.conn.executemany(
                    "INSERT INTO web_recovery_codes(operator_id,code_hash,created_at) "
                    "VALUES (?,?,?)",
                    [(operator_id, digest, now_text) for digest in code_hashes],
                )
                self._audit(
                    "web.operator.mfa.enrollment.completed",
                    actor_id=operator_id,
                    resource_id=operator_id,
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            self._mfa_enrollments.pop(token_hash, None)
            row = self.conn.execute(
                "SELECT * FROM web_operators WHERE id=?", (operator_id,)
            ).fetchone()
            # Enrollment has already persisted this OTP counter in the
            # preceding transaction. Issuing the first Web session must not
            # consume that same counter a second time (which now uses CAS).
            issued = self._issue_session(
                row, current=current, source_addr=source_addr, user_agent=user_agent,
            )
            return issued, recovery_codes

    def validate_session(
        self,
        token: str,
        *,
        csrf_token: Optional[str] = None,
        require_csrf: bool = False,
        now: Optional[datetime] = None,
    ) -> Optional[WebPrincipal]:
        raw = str(token or "").strip()
        if not raw:
            return None
        current = now or _utc_now()
        current_text = _utc_text(current)
        with self._lock:
            row = self.conn.execute(
                "SELECT s.*,o.username,o.role,o.enabled FROM web_sessions s "
                "JOIN web_operators o ON o.id=s.operator_id "
                "WHERE s.token_hash=?",
                (_sha256_text(raw),),
            ).fetchone()
            if not row or row["revoked_at"] is not None or not int(row["enabled"] or 0):
                return None
            try:
                expired = current >= _parse_utc(str(row["expires_at"]))
                idle_expired = current >= _parse_utc(str(row["idle_expires_at"]))
            except ValueError:
                expired = True
                idle_expired = True
            if expired or idle_expired:
                self.conn.execute(
                    "UPDATE web_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                    (current_text, row["id"]),
                )
                return None
            if require_csrf:
                supplied = _sha256_text(str(csrf_token or ""))
                if not hmac.compare_digest(supplied, str(row["csrf_hash"])):
                    return None
            try:
                last_seen = _parse_utc(str(row["last_seen_at"]))
            except ValueError:
                last_seen = current - timedelta(seconds=SESSION_REFRESH_SECONDS + 1)
            if (current - last_seen).total_seconds() >= SESSION_REFRESH_SECONDS:
                absolute_expiry = _parse_utc(str(row["expires_at"]))
                idle = min(
                    absolute_expiry,
                    current + timedelta(seconds=SESSION_IDLE_SECONDS),
                )
                self.conn.execute(
                    "UPDATE web_sessions SET last_seen_at=?,idle_expires_at=? "
                    "WHERE id=? AND revoked_at IS NULL",
                    (current_text, _utc_text(idle), row["id"]),
                )
            return WebPrincipal(
                operator_id=str(row["operator_id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                permissions=permissions_for_role(str(row["role"])),
                session_id=str(row["id"]),
            )

    def revoke_session(self, session_id: str, *, actor_id: str) -> bool:
        now = utc_now_iso()
        with self._lock:
            changed = self.conn.execute(
                "UPDATE web_sessions SET revoked_at=? "
                "WHERE id=? AND revoked_at IS NULL",
                (now, str(session_id)),
            ).rowcount
            if changed:
                self._audit(
                    "web.session.revoked",
                    actor_id=actor_id,
                    resource_id=str(session_id),
                )
            return changed == 1

    def revoke_operator_sessions(self, operator_id: str, *, actor_id: str) -> int:
        now = utc_now_iso()
        with self._lock:
            changed = self.conn.execute(
                "UPDATE web_sessions SET revoked_at=? "
                "WHERE operator_id=? AND revoked_at IS NULL",
                (now, str(operator_id)),
            ).rowcount
            self._audit(
                "web.session.revoke_all",
                actor_id=actor_id,
                resource_id=str(operator_id),
            )
            return int(changed or 0)

    def revoke_all_sessions(self, *, actor_id: str, reason: str = "restore") -> int:
        now = utc_now_iso()
        with self._lock:
            changed = self.conn.execute(
                "UPDATE web_sessions SET revoked_at=? WHERE revoked_at IS NULL",
                (now,),
            ).rowcount
            self._audit(
                "web.session.revoke_all_global",
                actor_id=actor_id,
                resource_id=str(reason or "system"),
            )
            self.conn.commit()
            return int(changed or 0)

    def list_sessions(self, operator_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id,created_at,last_seen_at,expires_at,idle_expires_at,revoked_at,"
            "source_addr,user_agent_hash FROM web_sessions "
            "WHERE operator_id=? ORDER BY created_at DESC LIMIT 100",
            (str(operator_id),),
        ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def recover_admin(
        self,
        *,
        username: str,
        new_password: str,
        totp_secret: str = "",
        recovery_codes: Optional[list[str]] = None,
        totp_value: str = "",
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        name = _validate_username(username)
        password = _validate_password(new_password)
        current = now or _utc_now()
        now_text = _utc_text(current)
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM web_operators WHERE username=? COLLATE NOCASE "
                "AND recovery_admin=1",
                (name,),
            ).fetchone()
            if not row:
                raise ControlPlaneError("Local recovery Admin was not found.")
            operator_id = str(row["id"])
            require_mfa = bool(int(row["mfa_required"] or 0))
            master: Optional[bytes] = None
            counter: Optional[int] = None
            cipher = ""
            code_hashes: list[str] = []
            if require_mfa:
                counter = verify_totp(totp_secret, totp_value, at=current)
                if counter is None:
                    raise ControlPlaneError("TOTP verification failed.")
                codes = list(recovery_codes or [])
                if len(codes) < 5:
                    raise ControlPlaneError("Recovery code set is incomplete.")
                master = _master_key(self.root)
                cipher = encrypt_token_pbkdf2(totp_secret, master)
                code_hashes = sorted({_recovery_hash(master, code) for code in codes})
            salt = os.urandom(16)
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "UPDATE web_operators SET password_salt=?,password_hash=?,"
                    "password_kdf=?,mfa_secret_ciphertext=?,mfa_enrolled=?,"
                    "mfa_last_counter=?,enabled=1,row_version=row_version+1,updated_at=? "
                    "WHERE id=?",
                    (
                        base64.b64encode(salt).decode("ascii"),
                        _password_hash(password, salt),
                        PASSWORD_KDF,
                        cipher,
                        1 if require_mfa else 0,
                        counter,
                        now_text,
                        operator_id,
                    ),
                )
                self.conn.execute(
                    "DELETE FROM web_recovery_codes WHERE operator_id=?",
                    (operator_id,),
                )
                if code_hashes:
                    self.conn.executemany(
                        "INSERT INTO web_recovery_codes(operator_id,code_hash,created_at) "
                        "VALUES (?,?,?)",
                        [(operator_id, digest, now_text) for digest in code_hashes],
                    )
                self.conn.execute(
                    "UPDATE web_sessions SET revoked_at=? "
                    "WHERE operator_id=? AND revoked_at IS NULL",
                    (now_text, operator_id),
                )
                self._audit(
                    "web.operator.local_recovery",
                    actor_id=operator_id,
                    resource_id=operator_id,
                    reason_code="MFA_ON" if require_mfa else "MFA_OFF",
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return {
            "operator_id": operator_id,
            "username": name,
            "recovered": True,
            "mfa_required": require_mfa,
            "mfa_enrolled": require_mfa,
        }

    def list_saved_views(self, operator_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id,name,payload_json,created_at,updated_at FROM web_saved_views "
            "WHERE operator_id=? ORDER BY name COLLATE NOCASE,id LIMIT 100",
            (str(operator_id),),
        ).fetchall()
        out = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except ValueError:
                payload = {}
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "payload": payload,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return out

    def save_view(
        self, operator_id: str, *, name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        view_name = str(name or "").strip()
        if not view_name or len(view_name) > 80:
            raise ControlPlaneError("Saved View name is required and must be at most 80 characters.")
        raw = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
        if len(raw.encode("utf-8")) > 8192:
            raise ControlPlaneError("Saved View exceeds the 8192-byte bound.")
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT id,created_at FROM web_saved_views "
            "WHERE operator_id=? AND name=? COLLATE NOCASE",
            (str(operator_id), view_name),
        ).fetchone()
        ident = str(existing["id"]) if existing else "wsv_" + secrets.token_hex(10)
        created = str(existing["created_at"]) if existing else now
        self.conn.execute(
            "INSERT INTO web_saved_views(id,operator_id,name,payload_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(operator_id,name) DO UPDATE SET "
            "payload_json=excluded.payload_json,updated_at=excluded.updated_at",
            (ident, str(operator_id), view_name, raw, created, now),
        )
        return {"id": ident, "name": view_name, "payload": payload or {}, "updated_at": now}
