#!/usr/bin/env python3
"""SQLite control-plane connection, schema, and migration ledger.

Authoritative path: /var/lib/drlink/drlink.db
Runtime JSON is derived state only.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

SCHEMA_VERSION = 3
APPLICATION_ID = 0x44524C4B  # 'DRLK'
DEFAULT_DB_REL = "var/lib/drlink/drlink.db"
BUSY_TIMEOUT_MS = 5000
READ_BUSY_TIMEOUT_MS = 500

SUPPORTED_PRAGMAS = (
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
    ("synchronous", "FULL"),
    ("busy_timeout", str(BUSY_TIMEOUT_MS)),
    ("trusted_schema", "OFF"),
)


class ControlPlaneError(Exception):
    """User-facing control-plane failure."""


class SchemaTooNewError(ControlPlaneError):
    def __init__(self, found: int, supported: int):
        super().__init__(
            "Control DB schema %s is newer than this binary (supports %s). "
            "No changes were applied."
            % (found, supported)
        )
        self.found = found
        self.supported = supported


class DatabaseCorruptError(ControlPlaneError):
    def __init__(self, detail: str = ""):
        msg = "Control DB is corrupt or unreadable. Enforcement is fail-closed."
        if detail:
            msg = "%s %s" % (msg, detail)
        super().__init__(msg)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(root: Optional[str] = None) -> str:
    if root:
        return str(root)
    for key in (
        "FRP_DEPLOY_TEST_ROOT",
        "FRP_CTL_TEST_ROOT",
        "FRP_SERVER_TEST_ROOT",
        "DRLINK_TEST_ROOT",
    ):
        value = os.environ.get(key) or ""
        if value:
            return value
    return ""


def macos_agent_state_root(host_root: Path) -> Path:
    """macOS Agent files live under Application Support, not /etc/frp.

    ``FRP_MACOS_STATE_ROOT`` overrides the live host only. A staging root
    keeps its own Application Support tree.
    """
    host = Path(host_root)
    if str(host) in ("/", ""):
        env = str(os.environ.get("FRP_MACOS_STATE_ROOT") or "").strip()
        if env:
            return Path(env)
    return host / "Library/Application Support/drlink"


def macos_agent_markers(state: Path) -> bool:
    if (state / "client-state.json").is_file():
        return True
    return (state / "frpc.toml").is_file() and (state / "client-identity.key").is_file()


def select_live_control_db(host_root: Path) -> Path:
    """Pick the control DB for a live host.

    A macOS Agent keeps ``drlink.db`` under Application Support/state. Opening
    ``/var/lib/drlink/drlink.db`` there creates an empty database, so ``show
    status`` misses the installed Agent and can report Role Unknown.

    ``FRP_MACOS_STATE_ROOT`` is an explicit live-host override. When it points
    at a valid macOS Agent state tree, honor it before probing Linux role
    markers under ``/etc``; this also keeps non-root diagnostics/tests from
    failing on unreadable host paths.
    """
    host = Path(host_root)
    state = macos_agent_state_root(host)
    linux_db = host / DEFAULT_DB_REL
    mac_override = (
        str(host) in ("/", "")
        and bool(str(os.environ.get("FRP_MACOS_STATE_ROOT") or "").strip())
    )
    if mac_override and macos_agent_markers(state):
        return state / "state" / "drlink.db"

    def _is_file(path: Path) -> bool:
        try:
            return path.is_file()
        except OSError:
            return False

    if (
        macos_agent_markers(state)
        and not _is_file(host / "etc/frp/client-state.json")
        and not _is_file(host / "etc/drlink/config.json")
    ):
        return state / "state" / "drlink.db"
    return linux_db


def db_path(root: Optional[str] = None) -> Path:
    base = resolve_root(root)
    if base:
        return Path(base) / DEFAULT_DB_REL
    return select_live_control_db(Path("/"))


def deploy_root_from_db_path(db_file) -> str:
    """Return <ROOT> for <ROOT>/var/lib/drlink/drlink.db.

    Real filesystem: ``/var/lib/drlink/drlink.db`` → ``/``.
    Staging/test: ``/tmp/test-root/var/lib/drlink/drlink.db`` → ``/tmp/test-root``.
    macOS Agent: ``<ROOT>/Library/Application Support/drlink/state/drlink.db``.

    Do not walk a fixed number of parents: ``Path.parent`` × 3 on the real DB
    path stops at ``/var`` and would create ``/var/var/lib/drlink``.
    """
    path = Path(db_file)
    mac_tail = ("Library", "Application Support", "drlink", "state", "drlink.db")
    parts = path.parts
    if len(parts) >= len(mac_tail) and parts[-len(mac_tail) :] == mac_tail:
        prefix = parts[: -len(mac_tail)]
        if not prefix or prefix == ("/",):
            return "/"
        return str(Path(*prefix))
    rel_parts = Path(DEFAULT_DB_REL).parts
    if len(parts) >= len(rel_parts) and parts[-len(rel_parts) :] == rel_parts:
        prefix = parts[: -len(rel_parts)]
        if not prefix or prefix == ("/",):
            return "/"
        return str(Path(*prefix))
    parts_list = list(parts)
    for idx, part in enumerate(parts_list):
        if part != "var":
            continue
        if parts_list[idx : idx + len(rel_parts)] != list(rel_parts):
            continue
        prefix = parts_list[:idx]
        if not prefix or prefix == ["/"]:
            return "/"
        return str(Path(*prefix))
    raise ControlPlaneError(
        "cannot derive deploy root from control db path %s" % path
    )


def runtime_dir(root: Optional[str] = None) -> Path:
    return db_path(root).parent / "runtime"


SCHEMA_SQL = r"""
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE system_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE config_revisions (
  revision INTEGER PRIMARY KEY,
  actor TEXT NOT NULL,
  command TEXT NOT NULL,
  created_at TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE revision_snapshots (
  revision INTEGER PRIMARY KEY,
  snapshot_json TEXT NOT NULL,
  FOREIGN KEY (revision) REFERENCES config_revisions(revision)
);

CREATE TABLE audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  revision INTEGER,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  before_summary TEXT,
  after_summary TEXT,
  impact_summary TEXT,
  result TEXT NOT NULL,
  FOREIGN KEY (revision) REFERENCES config_revisions(revision)
);

CREATE TABLE runtime_generations (
  plane TEXT PRIMARY KEY,
  db_revision INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  status TEXT NOT NULL,
  artifact_path TEXT,
  activated_at TEXT,
  error TEXT
);

CREATE TABLE objects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  type TEXT NOT NULL,
  origin TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  orphan_reason TEXT,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE object_values (
  object_id TEXT NOT NULL,
  value TEXT NOT NULL,
  normalized TEXT NOT NULL,
  PRIMARY KEY (object_id, value),
  FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
);

CREATE TABLE object_groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  description TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE object_group_members (
  group_id TEXT NOT NULL,
  member_kind TEXT NOT NULL,
  member_id TEXT NOT NULL,
  PRIMARY KEY (group_id, member_kind, member_id),
  FOREIGN KEY (group_id) REFERENCES object_groups(id) ON DELETE CASCADE
);

CREATE TABLE clients (
  id TEXT PRIMARY KEY,
  label TEXT,
  description TEXT,
  hostname TEXT,
  status TEXT NOT NULL DEFAULT 'connected',
  trust_status TEXT NOT NULL DEFAULT 'trusted',
  connected INTEGER NOT NULL DEFAULT 0,
  last_seen TEXT,
  agent_heartbeat_at TEXT,
  agent_lifecycle_state TEXT NOT NULL DEFAULT 'legacy',
  agent_platform TEXT,
  agent_version TEXT,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE managed_endpoints (
  id TEXT PRIMARY KEY,
  object_id TEXT NOT NULL UNIQUE,
  client_id TEXT,
  FOREIGN KEY (object_id) REFERENCES objects(id),
  FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE endpoint_addresses (
  endpoint_object_id TEXT NOT NULL,
  address TEXT NOT NULL,
  address_family TEXT NOT NULL,
  interface_name TEXT,
  scope TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  PRIMARY KEY (endpoint_object_id, address),
  FOREIGN KEY (endpoint_object_id) REFERENCES objects(id) ON DELETE CASCADE
);

CREATE TABLE client_groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  description TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE client_group_members (
  group_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  PRIMARY KEY (group_id, client_id),
  FOREIGN KEY (group_id) REFERENCES client_groups(id) ON DELETE CASCADE,
  FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE client_tags (
  client_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (client_id, key),
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE TABLE published_services (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  name TEXT NOT NULL,
  service_type TEXT NOT NULL,
  target_mode TEXT NOT NULL,
  target_host TEXT NOT NULL,
  target_port INTEGER NOT NULL,
  public_port INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1,
  released INTEGER NOT NULL DEFAULT 0,
  preset_name TEXT,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (client_id, name),
  FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE service_presets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  service_type TEXT,
  target_mode TEXT,
  target_port INTEGER,
  description TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE port_reservations (
  public_port INTEGER PRIMARY KEY,
  client_id TEXT,
  service_id TEXT,
  service_name TEXT,
  released INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE policy_rules (
  id TEXT PRIMARY KEY,
  plane TEXT NOT NULL,
  name TEXT NOT NULL COLLATE NOCASE,
  position INTEGER NOT NULL,
  action TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  description TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (plane, name)
);

CREATE TABLE rule_sources (
  rule_id TEXT NOT NULL,
  ref_kind TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (rule_id, ref_kind, ref_id),
  FOREIGN KEY (rule_id) REFERENCES policy_rules(id) ON DELETE CASCADE
);

CREATE TABLE rule_destinations (
  rule_id TEXT NOT NULL,
  ref_kind TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (rule_id, ref_kind, ref_id),
  FOREIGN KEY (rule_id) REFERENCES policy_rules(id) ON DELETE CASCADE
);

CREATE TABLE rule_services (
  rule_id TEXT NOT NULL,
  protocol TEXT NOT NULL,
  port INTEGER NOT NULL,
  PRIMARY KEY (rule_id, protocol, port),
  FOREIGN KEY (rule_id) REFERENCES policy_rules(id) ON DELETE CASCADE
);

CREATE TABLE enrollments (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  secret_ref TEXT
);

CREATE TABLE fixed_tcp (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  listen_port INTEGER,
  dest_host TEXT,
  dest_port INTEGER,
  destination_object_id TEXT,
  enabled INTEGER NOT NULL DEFAULT 0,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (destination_object_id) REFERENCES objects(id)
);

CREATE TABLE ai_principals (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  description TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 0,
  credential_hash TEXT,
  credential_fingerprint TEXT,
  credential_status TEXT NOT NULL DEFAULT 'none',
  last_seen TEXT,
  auth_mode TEXT NOT NULL DEFAULT 'static-bearer',
  oauth_issuer TEXT NOT NULL DEFAULT '',
  oauth_subject TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE ai_access_rules (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  principal_id TEXT,
  position INTEGER NOT NULL,
  action TEXT NOT NULL DEFAULT 'allow',
  enabled INTEGER NOT NULL DEFAULT 0,
  description TEXT NOT NULL DEFAULT '',
  exec_timeout INTEGER,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_rule_targets (
  rule_id TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  PRIMARY KEY (rule_id, target_kind, target_id),
  FOREIGN KEY (rule_id) REFERENCES ai_access_rules(id) ON DELETE CASCADE
);

CREATE TABLE ai_rule_capabilities (
  rule_id TEXT NOT NULL,
  capability TEXT NOT NULL,
  PRIMARY KEY (rule_id, capability),
  FOREIGN KEY (rule_id) REFERENCES ai_access_rules(id) ON DELETE CASCADE
);

CREATE TABLE ai_path_scopes (
  rule_id TEXT NOT NULL,
  pattern TEXT NOT NULL,
  PRIMARY KEY (rule_id, pattern),
  FOREIGN KEY (rule_id) REFERENCES ai_access_rules(id) ON DELETE CASCADE
);

CREATE TABLE ai_exec_constraints (
  rule_id TEXT PRIMARY KEY,
  timeout_seconds INTEGER,
  FOREIGN KEY (rule_id) REFERENCES ai_access_rules(id) ON DELETE CASCADE
);

CREATE TABLE ai_sessions (
  id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  credential_fingerprint TEXT,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_oauth_clients (
  client_id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  redirect_uris TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_oauth_codes (
  code_hash TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  resource TEXT NOT NULL DEFAULT '',
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_oauth_tokens (
  token_hash TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  client_id TEXT,
  resource TEXT NOT NULL DEFAULT '',
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  fingerprint TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_oauth_pending (
  id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  resource TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  completion_token TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TEXT NOT NULL DEFAULT '',
  decision_at TEXT NOT NULL DEFAULT '',
  consumed_at TEXT NOT NULL DEFAULT '',
  code_plain TEXT NOT NULL DEFAULT '',
  source_addr TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  principal_id TEXT,
  principal_name TEXT,
  endpoint_id TEXT,
  endpoint_name TEXT,
  capability TEXT NOT NULL,
  matched_rule TEXT,
  result TEXT NOT NULL,
  duration_ms INTEGER,
  revision INTEGER,
  operand_summary TEXT,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);

CREATE TABLE ai_jobs (
  id TEXT PRIMARY KEY,
  principal_id TEXT,
  endpoint_object_id TEXT,
  capability TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  timeout_seconds INTEGER,
  client_id TEXT,
  deadline_at TEXT,
  claim_token TEXT,
  attempt_id TEXT,
  claimed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_claim
  ON ai_jobs(status, client_id, created_at);

CREATE INDEX idx_objects_type ON objects(type);
CREATE INDEX idx_policy_plane_pos ON policy_rules(plane, position);
CREATE INDEX idx_ai_rules_pos ON ai_access_rules(position);
CREATE INDEX idx_ai_activity_principal ON ai_activity(principal_name, timestamp);
CREATE INDEX idx_audit_revision ON audit_events(revision);
"""


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = %s" % BUSY_TIMEOUT_MS)
    try:
        conn.execute("PRAGMA trusted_schema = OFF")
    except sqlite3.Error:
        pass
    try:
        conn.execute("PRAGMA application_id = %s" % APPLICATION_ID)
    except sqlite3.Error:
        pass


def current_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not row:
        return 0
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def integrity_check(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    if not row or str(row[0]).lower() != "ok":
        raise DatabaseCorruptError(str(row[0]) if row else "integrity_check failed")
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        raise DatabaseCorruptError("foreign key check failed (%s rows)" % len(fk))


def connect(path: Optional[Path] = None, root: Optional[str] = None, *, create: bool = True) -> sqlite3.Connection:
    target = Path(path) if path else db_path(root)
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() and not create:
        raise ControlPlaneError("Control DB does not exist: %s" % target)
    uri = "file:%s" % target
    conn = sqlite3.connect(
        uri, uri=True, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000.0, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    try:
        found = current_schema_version(conn) if target.exists() else 0
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise DatabaseCorruptError(str(exc)) from exc
    if found > SCHEMA_VERSION:
        conn.close()
        raise SchemaTooNewError(found, SCHEMA_VERSION)
    return conn


def connect_read_only(
    path: Optional[Path] = None,
    root: Optional[str] = None,
) -> sqlite3.Connection:
    """Open the authoritative DB without renegotiating write-affecting PRAGMAs.

    Public show/test/diff paths must not wait for the writer slot merely because
    a new SQLite connection is being initialized. The URI is mode=ro and
    query_only is enabled as a second fail-closed guard.
    """
    target = Path(path) if path else db_path(root)
    if not target.is_file():
        raise ControlPlaneError("Control DB does not exist: %s" % target)
    uri_path = quote(str(target.resolve()), safe="/:")
    uri = "file:%s?mode=ro" % uri_path
    conn = sqlite3.connect(
        uri,
        uri=True,
        isolation_level=None,
        timeout=READ_BUSY_TIMEOUT_MS / 1000.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = %s" % READ_BUSY_TIMEOUT_MS)
    try:
        conn.execute("PRAGMA trusted_schema = OFF")
    except sqlite3.Error:
        pass
    try:
        found = current_schema_version(conn)
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise DatabaseCorruptError(str(exc)) from exc
    if found > SCHEMA_VERSION:
        conn.close()
        raise SchemaTooNewError(found, SCHEMA_VERSION)
    if found < SCHEMA_VERSION:
        conn.close()
        raise ControlPlaneError(
            "Control DB schema %s requires migration before read-only access "
            "(current schema %s)." % (found, SCHEMA_VERSION)
        )
    return conn


AI_AUTH_SQL = r"""
CREATE TABLE IF NOT EXISTS ai_oauth_clients (
  client_id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  redirect_uris TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);
CREATE TABLE IF NOT EXISTS ai_oauth_codes (
  code_hash TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  resource TEXT NOT NULL DEFAULT '',
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);
CREATE TABLE IF NOT EXISTS ai_oauth_tokens (
  token_hash TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  client_id TEXT,
  resource TEXT NOT NULL DEFAULT '',
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  fingerprint TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);
CREATE TABLE IF NOT EXISTS ai_oauth_pending (
  id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  resource TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  completion_token TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TEXT NOT NULL DEFAULT '',
  decision_at TEXT NOT NULL DEFAULT '',
  consumed_at TEXT NOT NULL DEFAULT '',
  code_plain TEXT NOT NULL DEFAULT '',
  source_addr TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (principal_id) REFERENCES ai_principals(id)
);
CREATE TABLE IF NOT EXISTS ai_oauth_dcr_clients (
  client_id TEXT PRIMARY KEY,
  redirect_uris TEXT NOT NULL DEFAULT '',
  token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
  client_secret_hash TEXT,
  client_name TEXT NOT NULL DEFAULT '',
  metadata_url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
"""


def _ai_job_client_id_from_payload(payload_json: object) -> Optional[str]:
    """Extract a bindable client_id from legacy ai_jobs.payload_json.

    Returns a non-empty string only. Missing, malformed, or non-string values
    yield None so claim filtering cannot silently bind the wrong host.
    Does not use SQLite JSON1 (unavailable on Amazon Linux 2 Python builds).
    """
    if payload_json is None:
        return None
    try:
        raw = payload_json if isinstance(payload_json, str) else str(payload_json)
        doc = json.loads(raw)
    except (TypeError, ValueError, UnicodeError):
        return None
    if not isinstance(doc, dict):
        return None
    value = doc.get("client_id")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def ensure_ai_jobs_safety_schema(conn: sqlite3.Connection) -> None:
    """Additive AI job fairness/attempt columns without bumping SCHEMA_VERSION."""
    cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(ai_jobs)")}
    if not cols:
        return
    for name, ddl in (
        ("client_id", "ALTER TABLE ai_jobs ADD COLUMN client_id TEXT"),
        ("deadline_at", "ALTER TABLE ai_jobs ADD COLUMN deadline_at TEXT"),
        ("claim_token", "ALTER TABLE ai_jobs ADD COLUMN claim_token TEXT"),
        ("attempt_id", "ALTER TABLE ai_jobs ADD COLUMN attempt_id TEXT"),
        ("claimed_at", "ALTER TABLE ai_jobs ADD COLUMN claimed_at TEXT"),
    ):
        if name not in cols:
            conn.execute(ddl)
    # Backfill target host from legacy payload JSON so claim can filter in SQL.
    # Use Python JSON parsing — Amazon Linux 2's Python sqlite3 build lacks the
    # SQLite JSON1 SQL functions, and Server init must not depend on them.
    rows = list(
        conn.execute(
            "SELECT id, payload_json FROM ai_jobs "
            "WHERE client_id IS NULL OR client_id = ''"
        )
    )
    for row in rows:
        job_id = row[0]
        client_id = _ai_job_client_id_from_payload(row[1])
        if client_id is None:
            continue
        conn.execute(
            "UPDATE ai_jobs SET client_id = ? WHERE id = ? "
            "AND (client_id IS NULL OR client_id = '')",
            (client_id, job_id),
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_jobs_claim "
        "ON ai_jobs(status, client_id, created_at)"
    )


def ensure_ai_auth_schema(conn: sqlite3.Connection) -> None:
    """Additive AI auth tables/columns without bumping SCHEMA_VERSION."""
    cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(ai_principals)")}
    if cols and "auth_mode" not in cols:
        conn.execute(
            "ALTER TABLE ai_principals ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'static-bearer'"
        )
    if cols and "oauth_issuer" not in cols:
        conn.execute("ALTER TABLE ai_principals ADD COLUMN oauth_issuer TEXT NOT NULL DEFAULT ''")
    if cols and "oauth_subject" not in cols:
        conn.execute("ALTER TABLE ai_principals ADD COLUMN oauth_subject TEXT NOT NULL DEFAULT ''")
    conn.executescript(AI_AUTH_SQL)
    tok_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(ai_oauth_tokens)")}
    if tok_cols and "kind" not in tok_cols:
        conn.execute("ALTER TABLE ai_oauth_tokens ADD COLUMN kind TEXT NOT NULL DEFAULT 'access'")
    if tok_cols and "rotated_from" not in tok_cols:
        conn.execute("ALTER TABLE ai_oauth_tokens ADD COLUMN rotated_from TEXT")
    ensure_oauth_pending_completion_schema(conn)
    ensure_enrollment_plans_schema(conn)
    ensure_ai_jobs_safety_schema(conn)


def ensure_oauth_pending_completion_schema(conn: sqlite3.Connection) -> None:
    """Additive OAuth pending browser-completion columns without SCHEMA_VERSION bump."""
    cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(ai_oauth_pending)")}
    if not cols:
        return
    for name, ddl in (
        ("completion_token", "ALTER TABLE ai_oauth_pending ADD COLUMN completion_token TEXT NOT NULL DEFAULT ''"),
        ("status", "ALTER TABLE ai_oauth_pending ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"),
        ("expires_at", "ALTER TABLE ai_oauth_pending ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''"),
        ("decision_at", "ALTER TABLE ai_oauth_pending ADD COLUMN decision_at TEXT NOT NULL DEFAULT ''"),
        ("consumed_at", "ALTER TABLE ai_oauth_pending ADD COLUMN consumed_at TEXT NOT NULL DEFAULT ''"),
        ("code_plain", "ALTER TABLE ai_oauth_pending ADD COLUMN code_plain TEXT NOT NULL DEFAULT ''"),
        ("source_addr", "ALTER TABLE ai_oauth_pending ADD COLUMN source_addr TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in cols:
            conn.execute(ddl)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_oauth_pending_completion_token "
        "ON ai_oauth_pending(completion_token)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_oauth_pending_source_addr "
        "ON ai_oauth_pending(source_addr)"
    )


ENROLLMENT_PLANS_SQL = """
CREATE TABLE IF NOT EXISTS enrollment_plans (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  platform TEXT NOT NULL DEFAULT 'linux',
  client_groups_json TEXT NOT NULL DEFAULT '[]',
  initial_services_json TEXT NOT NULL DEFAULT '[]',
  description TEXT NOT NULL DEFAULT '',
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def ensure_enrollment_plans_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ENROLLMENT_PLANS_SQL)


def ensure_agent_lifecycle_schema(conn: sqlite3.Connection) -> None:
    """Add Agent presence fields without changing the v2 schema contract."""
    cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(clients)")}
    if not cols:
        return
    if "agent_heartbeat_at" not in cols:
        conn.execute("ALTER TABLE clients ADD COLUMN agent_heartbeat_at TEXT")
    if "agent_lifecycle_state" not in cols:
        conn.execute(
            "ALTER TABLE clients ADD COLUMN agent_lifecycle_state TEXT NOT NULL DEFAULT 'legacy'"
        )


V30_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS emergency_cutoffs (
  id TEXT PRIMARY KEY,
  plane TEXT NOT NULL,
  scope_kind TEXT NOT NULL,
  scope_ref TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  reason TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (plane, scope_kind, scope_ref)
);

CREATE INDEX IF NOT EXISTS idx_emergency_cutoffs_active
  ON emergency_cutoffs(active, plane, scope_kind, scope_ref);

CREATE TABLE IF NOT EXISTS management_change_plans (
  token_hash TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL,
  server_id TEXT NOT NULL,
  operation_class TEXT NOT NULL,
  operation TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_ref TEXT NOT NULL,
  expected_revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  impact_json TEXT NOT NULL DEFAULT '{}',
  confirmation_class TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_management_change_plans_actor
  ON management_change_plans(actor_id, status, expires_at);

CREATE TABLE IF NOT EXISTS management_jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  resource_type TEXT NOT NULL DEFAULT '',
  resource_ref TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'QUEUED',
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  target_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  deadline_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_management_jobs_status_time
  ON management_jobs(status, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_management_jobs_type_time
  ON management_jobs(job_type, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS management_job_targets (
  job_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  worker_id TEXT NOT NULL DEFAULT '',
  claim_token TEXT NOT NULL DEFAULT '',
  attempt INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  finished_at TEXT,
  lease_expires_at TEXT,
  updated_at TEXT NOT NULL,
  result_json TEXT NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (job_id, target_id),
  FOREIGN KEY (job_id) REFERENCES management_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_management_job_targets_claim
  ON management_job_targets(status, updated_at, job_id, target_id);
CREATE INDEX IF NOT EXISTS idx_management_job_targets_job_status
  ON management_job_targets(job_id, status, target_id);

CREATE TABLE IF NOT EXISTS audit_ingest_checkpoints (
  source TEXT PRIMARY KEY,
  last_sequence INTEGER NOT NULL DEFAULT 0,
  last_segment TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS web_operators (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  role TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  recovery_admin INTEGER NOT NULL DEFAULT 0,
  password_salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  password_kdf TEXT NOT NULL,
  mfa_secret_ciphertext TEXT NOT NULL,
  mfa_enrolled INTEGER NOT NULL DEFAULT 0,
  mfa_last_counter INTEGER,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_login_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_web_operators_role
  ON web_operators(role, enabled, username);

CREATE TABLE IF NOT EXISTS web_recovery_codes (
  operator_id TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consumed_at TEXT,
  PRIMARY KEY (operator_id, code_hash),
  FOREIGN KEY (operator_id) REFERENCES web_operators(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS web_sessions (
  id TEXT PRIMARY KEY,
  operator_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  idle_expires_at TEXT NOT NULL,
  revoked_at TEXT,
  source_addr TEXT NOT NULL DEFAULT '',
  user_agent_hash TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (operator_id) REFERENCES web_operators(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_web_sessions_operator
  ON web_sessions(operator_id, revoked_at, expires_at);
CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry
  ON web_sessions(revoked_at, expires_at, idle_expires_at);

CREATE TABLE IF NOT EXISTS web_saved_views (
  id TEXT PRIMARY KEY,
  operator_id TEXT NOT NULL,
  name TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(operator_id, name),
  FOREIGN KEY (operator_id) REFERENCES web_operators(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS management_policy_tests (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  plane TEXT NOT NULL,
  source TEXT NOT NULL,
  destination TEXT NOT NULL,
  service TEXT NOT NULL DEFAULT '',
  permission TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  expected TEXT NOT NULL,
  required INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_revision INTEGER,
  updated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_management_policy_tests_plane
  ON management_policy_tests(plane, enabled, required, name);

CREATE TABLE IF NOT EXISTS management_drafts (
  id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL,
  bundle_text TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'DRAFT',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  applied_revision INTEGER,
  last_error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_management_drafts_actor_status
  ON management_drafts(actor_id, status, updated_at DESC, id DESC);
"""


def ensure_v30_schema(conn: sqlite3.Connection) -> None:
    """Install additive 3.0 management primitives on the authoritative DB."""
    client_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(clients)")}
    if client_cols and "agent_platform" not in client_cols:
        conn.execute("ALTER TABLE clients ADD COLUMN agent_platform TEXT")
    if client_cols and "agent_version" not in client_cols:
        conn.execute("ALTER TABLE clients ADD COLUMN agent_version TEXT")
    policy_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(policy_rules)")}
    if policy_cols and "expires_at" not in policy_cols:
        conn.execute("ALTER TABLE policy_rules ADD COLUMN expires_at TEXT")
    ai_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(ai_policy_rules)")}
    if ai_cols and "expires_at" not in ai_cols:
        conn.execute("ALTER TABLE ai_policy_rules ADD COLUMN expires_at TEXT")

    audit_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(audit_events)")}
    audit_additions = (
        ("event_id", "TEXT"),
        ("schema_version", "INTEGER"),
        ("category", "TEXT"),
        ("event_type", "TEXT"),
        ("occurred_at", "TEXT"),
        ("source", "TEXT"),
        ("source_sequence", "INTEGER"),
        ("actor_type", "TEXT"),
        ("actor_id", "TEXT"),
        ("delegated_actor_id", "TEXT"),
        ("interface", "TEXT"),
        ("reason_code", "TEXT"),
        ("correlation_id", "TEXT"),
        ("request_id", "TEXT"),
        ("session_id", "TEXT"),
        ("revision_before", "INTEGER"),
        ("revision_after", "INTEGER"),
        ("matched_policy_json", "TEXT"),
        ("source_meta_json", "TEXT"),
        ("destination_meta_json", "TEXT"),
        ("duration_ms", "INTEGER"),
    )
    for column, decl in audit_additions:
        if audit_cols and column not in audit_cols:
            conn.execute("ALTER TABLE audit_events ADD COLUMN %s %s" % (column, decl))

    # Existing 2.x control audit remains queryable through the 3.0 envelope.
    # event_id stays NULL for historical rows; new writes receive stable IDs.
    conn.execute(
        "UPDATE audit_events SET "
        "schema_version=COALESCE(schema_version,1),"
        "category=COALESCE(category,'CONTROL'),"
        "event_type=COALESCE(event_type,operation),"
        "occurred_at=COALESCE(occurred_at,timestamp),"
        "source=COALESCE(source,'legacy-core'),"
        "actor_type=COALESCE(actor_type,'operator'),"
        "actor_id=COALESCE(actor_id,actor),"
        "interface=COALESCE(interface,'LEGACY'),"
        "revision_after=COALESCE(revision_after,revision),"
        "revision_before=COALESCE("
        "revision_before,CASE WHEN revision > 0 THEN revision - 1 ELSE NULL END)"
    )

    conn.executescript(V30_SCHEMA_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_policy_rules_expiry "
        "ON policy_rules(plane, enabled, expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_policy_rules_expiry "
        "ON ai_policy_rules(enabled, expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_clients_label "
        "ON clients(label COLLATE NOCASE, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_clients_hostname "
        "ON clients(hostname COLLATE NOCASE, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_clients_status "
        "ON clients(status, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_clients_agent_version "
        "ON clients(agent_version, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_clients_platform "
        "ON clients(agent_platform, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_services_state "
        "ON published_services(enabled, released, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_policy_plane_enabled_pos "
        "ON policy_rules(plane, enabled, position, id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_v30_audit_event_id "
        "ON audit_events(event_id) WHERE event_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_audit_time "
        "ON audit_events(occurred_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_audit_category_time "
        "ON audit_events(category, occurred_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_audit_actor_time "
        "ON audit_events(actor_id, occurred_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_audit_resource_time "
        "ON audit_events(entity_type, entity_id, occurred_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_v30_audit_correlation "
        "ON audit_events(correlation_id, occurred_at DESC, id DESC)"
    )


LEGACY_AI_ACTIVITY_CONVERGENCE_BATCH = 200


def converge_legacy_ai_activity(
    conn: sqlite3.Connection,
    *,
    limit: int = LEGACY_AI_ACTIVITY_CONVERGENCE_BATCH,
) -> dict:
    """Boundedly converge legacy ai_activity rows into unified v3 audit_events.

    ai_activity remains a compatibility migration source only. New 3.0 activity
    is written directly to audit_events; this routine adopts the legacy
    companion audit row when one exists, avoiding duplicate history.
    """
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('ai_activity','audit_events')"
        ).fetchall()
    }
    if {"ai_activity", "audit_events"} - tables:
        return {"processed": 0, "remaining": 0}

    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(audit_events)")
    }
    required = {
        "event_id",
        "schema_version",
        "category",
        "event_type",
        "occurred_at",
        "source",
        "source_sequence",
        "actor_type",
        "actor_id",
        "interface",
        "revision_after",
        "matched_policy_json",
        "source_meta_json",
        "destination_meta_json",
        "duration_ms",
    }
    if not required <= columns:
        return {"processed": 0, "remaining": 0}

    batch = max(1, min(int(limit), 1000))
    rows = conn.execute(
        "SELECT a.* FROM ai_activity a "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM audit_events e "
        "WHERE e.source='legacy-ai_activity' AND e.source_sequence=a.id"
        ") ORDER BY a.id DESC LIMIT ?",
        (batch,),
    ).fetchall()
    if not rows:
        return {"processed": 0, "remaining": 0}

    processed = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            ident = int(row["id"])
            occurred = str(row["timestamp"])
            principal = str(row["principal_name"] or "")
            endpoint = str(row["endpoint_name"] or "")
            capability = str(row["capability"] or "")
            result = str(row["result"] or "")
            matched = str(row["matched_rule"] or "")
            revision = row["revision"]
            revision_fk = (
                int(revision) if revision is not None and int(revision) > 0 else None
            )
            operand = str(row["operand_summary"] or "")[:200]
            duration = row["duration_ms"]
            event_id = "legacy-ai-activity-%020d" % ident
            matched_json = json.dumps(
                [matched] if matched else [],
                sort_keys=True,
                separators=(",", ":"),
            )
            source_meta = json.dumps(
                {"ai_identity": principal} if principal else {},
                sort_keys=True,
                separators=(",", ":"),
            )
            destination_meta = json.dumps(
                {"host": endpoint} if endpoint else {},
                sort_keys=True,
                separators=(",", ":"),
            )

            # v2.4 record_ai_activity dual-wrote a companion audit row. Adopt it
            # in place when possible so convergence does not duplicate history.
            candidate = conn.execute(
                "SELECT id FROM audit_events "
                "WHERE event_id IS NULL AND timestamp=? AND actor=? "
                "AND action=? AND operation=? AND result=? "
                "ORDER BY id DESC LIMIT 1",
                (
                    occurred,
                    principal,
                    "ai %s" % capability,
                    capability,
                    result,
                ),
            ).fetchone()
            if candidate:
                conn.execute(
                    "UPDATE audit_events SET "
                    "event_id=?,schema_version=1,category='ACCESS_DECISION',"
                    "event_type='ai.tool',occurred_at=?,source='legacy-ai_activity',"
                    "source_sequence=?,actor_type='ai-identity',actor_id=?,"
                    "interface='MCP',entity_type='managed-endpoint',entity_id=?,"
                    "revision_after=COALESCE(revision_after,revision),"
                    "matched_policy_json=?,source_meta_json=?,destination_meta_json=?,"
                    "after_summary=?,duration_ms=? WHERE id=?",
                    (
                        event_id,
                        occurred,
                        ident,
                        principal,
                        endpoint,
                        matched_json,
                        source_meta,
                        destination_meta,
                        operand,
                        duration,
                        int(candidate["id"]),
                    ),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO audit_events("
                    "timestamp,revision,actor,action,entity_type,entity_id,operation,"
                    "before_summary,after_summary,impact_summary,result,event_id,"
                    "schema_version,category,event_type,occurred_at,source,source_sequence,"
                    "actor_type,actor_id,delegated_actor_id,interface,reason_code,"
                    "correlation_id,request_id,session_id,revision_before,revision_after,"
                    "matched_policy_json,source_meta_json,destination_meta_json,duration_ms"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        occurred,
                        revision_fk,
                        principal,
                        "ai %s" % capability,
                        "managed-endpoint",
                        endpoint,
                        capability,
                        "",
                        operand,
                        "",
                        result,
                        event_id,
                        1,
                        "ACCESS_DECISION",
                        "ai.tool",
                        occurred,
                        "legacy-ai_activity",
                        ident,
                        "ai-identity",
                        principal,
                        "",
                        "MCP",
                        "",
                        "",
                        "",
                        "",
                        None,
                        revision,
                        matched_json,
                        source_meta,
                        destination_meta,
                        duration,
                    ),
                )
            processed += 1
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise

    remaining = int(
        conn.execute(
            "SELECT COUNT(*) FROM ai_activity a "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM audit_events e "
            "WHERE e.source='legacy-ai_activity' AND e.source_sequence=a.id"
            ")"
        ).fetchone()[0]
        or 0
    )
    conn.execute(
        "INSERT OR REPLACE INTO system_meta(key,value) VALUES (?,?)",
        (
            "v30_ai_activity_convergence",
            "complete" if remaining == 0 else "in-progress",
        ),
    )
    return {"processed": processed, "remaining": remaining}


def initialize(conn: sqlite3.Connection) -> None:
    from drlink_v24 import ensure_v2_schema

    found = current_schema_version(conn)
    if found > SCHEMA_VERSION:
        raise SchemaTooNewError(found, SCHEMA_VERSION)
    if found == SCHEMA_VERSION:
        ensure_ai_auth_schema(conn)
        ensure_v2_schema(conn)
        ensure_v30_schema(conn)
        ensure_agent_lifecycle_schema(conn)
        integrity_check(conn)
        return

    if found == 0:
        conn.executescript(SCHEMA_SQL)
        ensure_v2_schema(conn)
        ensure_v30_schema(conn)
        ensure_agent_lifecycle_schema(conn)
        now = utc_now_iso()
        conn.execute("BEGIN IMMEDIATE")
        try:
            for version, name in (
                (1, "initial_control_plane"),
                (2, "v24_canonical_objects_policy"),
                (3, "v30_management_foundation"),
            ):
                conn.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, now),
                )
            conn.execute(
                "INSERT OR REPLACE INTO system_meta(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO system_meta(key, value) VALUES (?, ?)",
                ("created_at", now),
            )
            for plane, status in (
                ("remote", "active"),
                ("internet", "active"),
                ("ai", "not_configured"),
            ):
                conn.execute(
                    "INSERT OR REPLACE INTO runtime_generations"
                    "(plane, db_revision, generation, status, artifact_path, activated_at, error) "
                    "VALUES (?, 0, 0, ?, '', ?, '')",
                    (plane, status, now),
                )
            integrity_check(conn)
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        ensure_ai_auth_schema(conn)
        return

    if found == 1:
        ensure_v2_schema(conn)
        ensure_v30_schema(conn)
        ensure_agent_lifecycle_schema(conn)
        now = utc_now_iso()
        conn.execute("BEGIN IMMEDIATE")
        try:
            for version, name in (
                (2, "v24_canonical_objects_policy"),
                (3, "v30_management_foundation"),
            ):
                conn.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, now),
                )
            conn.execute(
                "INSERT OR REPLACE INTO system_meta(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            integrity_check(conn)
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        ensure_ai_auth_schema(conn)
        return

    if found == 2:
        ensure_v2_schema(conn)
        ensure_v30_schema(conn)
        ensure_agent_lifecycle_schema(conn)
        ensure_ai_auth_schema(conn)
        now = utc_now_iso()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (3, "v30_management_foundation", now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO system_meta(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            integrity_check(conn)
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return

    raise ControlPlaneError("Unknown control DB schema %s" % found)


def open_control_db(root: Optional[str] = None, *, create: bool = True) -> sqlite3.Connection:
    conn = connect(root=root, create=create)
    initialize(conn)
    # Fully converge legacy AI activity before returning the writable Core DB,
    # but keep every writer hold bounded to one migration batch.
    while True:
        state = converge_legacy_ai_activity(conn)
        if int(state.get("remaining") or 0) == 0:
            break
        if int(state.get("processed") or 0) == 0:
            conn.close()
            raise ControlPlaneError("Legacy AI activity convergence made no progress.")
    return conn


def open_control_db_readonly(root: Optional[str] = None) -> sqlite3.Connection:
    return connect_read_only(root=root)


def pragma_snapshot(conn: sqlite3.Connection) -> dict:
    out = {}
    for name, _expected in SUPPORTED_PRAGMAS:
        try:
            row = conn.execute("PRAGMA %s" % name).fetchone()
            out[name] = row[0] if row else None
        except sqlite3.Error:
            out[name] = None
    return out
