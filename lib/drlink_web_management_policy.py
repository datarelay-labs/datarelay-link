"""Strict, offline, opt-in Web ingress configuration for Link 3.0.

The local product/service operator selects the file explicitly. No network,
database, host firewall, sshd, runtime reload, or secret access is performed.
The source decisions remain those of the exact pinned Foundation ACL wheel.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from dataclasses import dataclass

from drlink_foundation_security import (
    FoundationAllowEntry,
    FoundationManagementPolicy,
    FoundationSurfacePolicy,
    foundation_authorize_management,
    foundation_canonical_network,
)

MAX_CONFIG_BYTES = 16_384
MAX_SOURCES = 128
MAX_PROXIES = 16
_REVISION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")


@dataclass(frozen=True)
class WebIngressConfiguration:
    policy: FoundationManagementPolicy
    trusted_proxy_cidrs: tuple[str, ...]


def _reject_extra(value: object, required: set[str], optional: set[str] = set()) -> dict:
    if type(value) is not dict or required - value.keys() or value.keys() - (required | optional):
        raise ValueError("invalid Web ingress configuration fields")
    return value


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate ingress configuration field")
        result[key] = value
    return result


def _decode(data: bytes) -> WebIngressConfiguration:
    try:
        content = json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Web ingress configuration JSON") from exc
    config = _reject_extra(
        content, {"schema_version", "web"}, {"trusted_proxy_cidrs"}
    )
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("unsupported Web ingress configuration version")

    web = _reject_extra(config["web"], {"enabled", "revision", "sources"})
    if type(web["enabled"]) is not bool:
        raise ValueError("invalid Web ingress enabled flag")
    revision = web["revision"]
    if type(revision) is not str or _REVISION.fullmatch(revision) is None:
        raise ValueError("invalid Web ingress policy revision")
    rows = web["sources"]
    if type(rows) is not list or len(rows) > MAX_SOURCES:
        raise ValueError("too many Web ingress sources")
    sources = []
    for row in rows:
        item = _reject_extra(row, {"cidr"}, {"name", "expires_at"})
        if type(item["cidr"]) is not str:
            raise ValueError("invalid Web ingress source CIDR")
        if "name" in item and type(item["name"]) is not str:
            raise ValueError("invalid Web ingress source name")
        if "expires_at" in item and (
            type(item["expires_at"]) is not int or item["expires_at"] <= 0
        ):
            raise ValueError("invalid Web ingress source expiry")
        sources.append(
            FoundationAllowEntry(
                item["cidr"], name=item.get("name", ""),
                expires_at=item.get("expires_at"),
            )
        )
    proxy_rows = config.get("trusted_proxy_cidrs", [])
    if type(proxy_rows) is not list or len(proxy_rows) > MAX_PROXIES:
        raise ValueError("invalid trusted proxy list")
    proxies = []
    for cidr in proxy_rows:
        if type(cidr) is not str:
            raise ValueError("invalid trusted proxy CIDR")
        proxies.append(foundation_canonical_network(cidr))
    if len(set(proxies)) != len(proxies):
        raise ValueError("duplicate trusted proxy CIDR")
    web_policy = FoundationSurfacePolicy(
        enabled=web["enabled"], revision=revision, sources=tuple(sources),
    )
    return WebIngressConfiguration(
        FoundationManagementPolicy(web=web_policy), tuple(proxies),
    )


def load_management_ingress(path: str) -> WebIngressConfiguration:
    """Read a single host-admin-selected, owner-private regular JSON file.

    Fails closed if the exact configured path is absent, not private, symlinked,
    hard-linked, oversized, malformed, or not owned by root/service uid.
    Reading the verified fd (not reopening by path) avoids a final-component
    symlink or replacement race. No live policy change is attempted.
    """
    if type(path) is not str or not path.startswith("/") or "\x00" in path:
        raise ValueError("management ingress policy needs an absolute file path")
    # Validate literal components before opening; Path.resolve() and a final
    # O_NOFOLLOW alone would follow a symlink in any ancestor directory.
    components = path.split("/")
    if len(components) < 2 or any(
        not component or component in (".", "..") for component in components[1:]
    ):
        raise ValueError("noncanonical Web ingress configuration path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("secure no-follow path traversal unavailable")
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | close_on_exec
    )
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | close_on_exec
    directory_fd = None
    file_fd = None
    try:
        # Walk each component with directory descriptors. The final policy
        # file is opened only under the verified parent descriptor; no
        # path-level reopen or trust in a symlinked parent.
        directory_fd = os.open("/", directory_flags)
        for component in components[1:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(components[-1], flags, dir_fd=directory_fd)
        info = os.fstat(file_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid not in (0, os.geteuid())
            or info.st_mode & 0o077
            or not 0 < info.st_size <= MAX_CONFIG_BYTES
        ):
            raise ValueError("untrusted Web ingress configuration file")
        raw = os.read(file_fd, MAX_CONFIG_BYTES + 1)
        final = os.fstat(file_fd)
        if (
            len(raw) != info.st_size
            or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)
            != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns, final.st_nlink)
        ):
            raise ValueError("Web ingress configuration changed during read")
    except OSError as exc:
        raise ValueError("unavailable trusted Web ingress configuration file") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)
    return _decode(raw)


def preview_management_ingress(
    *, policy_file: str, source_peer: str | None,
    forwarded_for: str | None = None, now: int | None = None,
) -> dict:
    """Only simulate an operator-supplied management source against local ACL.

    Neither peer provenance nor deployed Web listener configuration is
    observed. Even a matching CIDR CANNOT authorize a live policy switch,
    SSH access change, or recovery commitment.
    """
    if type(source_peer) not in (str, type(None)):
        raise ValueError("invalid simulated management source")
    if type(forwarded_for) not in (str, type(None)):
        raise ValueError("invalid simulated proxy chain")
    if type(now) is not int and now is not None:
        raise ValueError("invalid simulation timestamp")
    if now is None:
        now = int(time.time())
    if now < 0:
        raise ValueError("invalid simulation timestamp")
    for value in (source_peer, forwarded_for):
        if value is not None and (
            len(value) > 1024 or any(character in value for character in "\r\n\x00")
        ):
            raise ValueError("invalid simulated management source")

    configured = load_management_ingress(policy_file)
    web = configured.policy.web
    match = foundation_authorize_management(
        configured.policy, "web",
        direct_peer=source_peer,
        x_forwarded_for=forwarded_for,
        trusted_proxy_cidrs=configured.trusted_proxy_cidrs,
        now=now,
    )
    # Disabled policy permits HTTP traffic for compatibility, but that does
    # not establish an allowlist, nor prove the operator's access path.
    simulation = (
        "NOT_ENFORCED" if not web.enabled else "ALLOW" if match.allowed else "DENY"
    )
    blockers = [
        "observed_management_path_unverified",
        "rollback_unverified",
        "offline_console_unverified",
        "two_user_acceptance_unverified",
        "ssh_host_enforcement_unavailable",
    ]
    if not web.enabled:
        blockers.insert(0, "web_policy_disabled")
    elif not match.allowed:
        blockers.insert(0, "simulation_did_not_allow_source")
    return {
        "status": "BLOCKED",
        "management_source_simulation": simulation,
        "policy_enabled": bool(web.enabled),
        "policy_revision": web.revision,
        "source_count": len(web.sources),
        "trusted_proxy_count": len(configured.trusted_proxy_cidrs),
        "caller_supplied_source_only": True,
        "authoritative_peer_observed": False,
        "runtime_policy_observed": False,
        "rollback_verified": False,
        "ssh_host_enforced": False,
        "safe_to_activate": False,
        "read_only": True,
        "blockers": blockers,
    }
