"""PF-12A Link product-owned, count-only historical revision observation.

Reads authoritative Link Core revision snapshots through read-only SQLite, but
never returns ConfigurationBundle entries, object names, addresses, actors or
secrets. This is category-count comparison, NOT a full semantic diff or
authorization to restore historical data. The pinned Foundation wheel owns the
only diff and advisory rollback-preflight implementations.
"""
from __future__ import annotations

import yaml

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from drlink_foundation_security import (
    FoundationConfigField, FoundationConfigRevision,
    FoundationRollbackEvidence, foundation_diff_configurations,
    foundation_preview_config_rollback,
)

MAX_SNAPSHOT_CHARS = 128 * 1024
MAX_ITEMS_PER_SECTION = 1024
_SECTION_LISTS = {
    "networkObjects": "network_objects",
    "networkGroups": "network_groups",
    "serviceObjects": "service_objects",
    "serviceGroups": "service_groups",
    "permissionObjects": "permission_objects",
    "permissionGroups": "permission_groups",
    "remoteServices": "remote_services",
}
_POLICY_SECTIONS = {
    "remoteAccess": "remote_access",
    "internetAccess": "internet_access",
    "aiAccess": "ai_access",
}
_SAFE_KEYS = frozenset(
    list(_SECTION_LISTS.values())
    + [name + suffix for name in _POLICY_SECTIONS.values()
       for suffix in ("_rules", "_enabled_rules")]
)
_CANONICAL_KEYS = set(_SECTION_LISTS) | set(_POLICY_SECTIONS) | {
    "context", "sourceRevision",
}


class _NoAliasNoDuplicatesLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ValueError("configuration aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("configuration mapping is malformed")
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str or key in result:
                raise ValueError("configuration mapping contains an invalid key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _configuration_counts(snapshot: str, expected_revision: int) -> dict[str, int]:
    if (type(snapshot) is not str or not 0 < len(snapshot) <= MAX_SNAPSHOT_CHARS
            or "\x00" in snapshot):
        raise ValueError("configuration history snapshot unavailable")
    data = yaml.load(snapshot, Loader=_NoAliasNoDuplicatesLoader)
    if type(data) is not dict or set(data) != {"configurationBundle"}:
        raise ValueError("configuration history document unavailable")
    bundle = data["configurationBundle"]
    if (
        type(bundle) is not dict
        or set(bundle) - _CANONICAL_KEYS
        or bundle.get("context") not in ("server", "agent")
        or type(bundle.get("sourceRevision")) is not int
        or bundle["sourceRevision"] != expected_revision
    ):
        raise ValueError("configuration history revision mismatch")
    counts = {key: 0 for key in _SAFE_KEYS}
    for section, safe_name in _SECTION_LISTS.items():
        entries = bundle.get(section, [])
        if (
            type(entries) is not list
            or len(entries) > MAX_ITEMS_PER_SECTION
            or any(type(entry) is not dict for entry in entries)
        ):
            raise ValueError("configuration history item counts unavailable")
        counts[safe_name] = len(entries)
    for section, safe_name in _POLICY_SECTIONS.items():
        policy = bundle.get(section)
        if policy is None:
            continue
        if type(policy) is not dict or not {"mode", "rules"} <= set(policy):
            raise ValueError("configuration history policy unavailable")
        rules = policy["rules"]
        if (
            type(rules) is not list
            or len(rules) > MAX_ITEMS_PER_SECTION
            or any(type(entry) is not dict for entry in rules)
        ):
            raise ValueError("configuration history rules unavailable")
        counts[safe_name + "_rules"] = len(rules)
        counts[safe_name + "_enabled_rules"] = sum(
            1 for rule in rules if rule.get("enabled") is True
        )
    return counts


def _revision_id(value: object) -> int:
    if type(value) is int:
        number = value
    elif type(value) is str and value.isascii() and value.isdecimal() and len(value) <= 10:
        number = int(value)
    else:
        raise ControlPlaneError("Configuration revision must be a positive integer.")
    if not 1 <= number <= 2_147_483_647:
        raise ControlPlaneError("Configuration revision is outside supported limits.")
    return number


def _safe_revision(plane: ControlPlane, revision: int) -> FoundationConfigRevision:
    try:
        snapshot = plane.revision_snapshot(revision)
        if (
            snapshot.get("snapshot_format") != "drlink-revision-configuration-v1"
            or type(snapshot.get("configuration_bundle")) is not str
        ):
            raise ValueError("historical snapshot is absent")
        counts = _configuration_counts(snapshot["configuration_bundle"], revision)
        return FoundationConfigRevision(
            product_ref="drlink",
            revision_ref="rev." + str(revision),
            actor_ref="product.core",
            created_at=revision,  # sequence order, not simulated event timestamp
            fields=tuple(FoundationConfigField(key, counts[key])
                         for key in sorted(counts)),
        )
    except Exception:
        # Do not leak exception strings: legacy snapshot errors can contain
        # raw ConfigurationBundle text, real actors/addresses or secrets.
        raise ControlPlaneError("Configuration revision snapshot is unavailable.") from None


def compare_product_revisions(
    root: str | None,
    from_revision: int | str,
    to_revision: int | str,
) -> dict:
    """Summarize observed categories only; NEVER enable a rollback."""
    first = _revision_id(from_revision)
    second = _revision_id(to_revision)
    if first >= second:
        raise ControlPlaneError("Comparison requires ascending historical revisions.")
    try:
        plane = ControlPlane(root, read_only=True)
        try:
            current = plane.current_revision()
            previous_snapshot = _safe_revision(plane, first)
            latest_snapshot = _safe_revision(plane, second)
        finally:
            plane.close()
    except Exception:
        # SQLite open/parse errors can contain private DB paths or SQL details.
        # Never send those strings over an authenticated Web API response.
        raise ControlPlaneError(
            "Configuration revision snapshot is unavailable."
        ) from None
    diff = foundation_diff_configurations(
        previous_snapshot, latest_snapshot, allowlisted_paths=_SAFE_KEYS,
    )
    # Deliberately false evidence. A Web historical diff is not authority to
    # mutate configuration, claim MFA, assume backups or bypass recovery.
    preview = foundation_preview_config_rollback(
        latest_snapshot, previous_snapshot, allowlisted_paths=_SAFE_KEYS,
        reversible_paths=frozenset(),
        evidence=FoundationRollbackEvidence(
            expected_current_revision="rev." + str(current),
            target_revision_available=True,
        ),
    )
    count_from = {field.path: int(field.value) for field in previous_snapshot.fields}
    count_to = {field.path: int(field.value) for field in latest_snapshot.fields}
    return {
        "from_revision": first,
        "to_revision": second,
        "source_scope": "allowlisted_counts_only",
        "read_only": True,
        "authoritative_mutation": False,
        "full_semantic_diff_verified": False,
        "semantic_equivalence_proven": False,
        "changed_categories": len(diff.changes),
        "counts": {"from": count_from, "to": count_to},
        "changes": [
            {
                "category": item.path,
                "before_count": int(item.before or "0"),
                "after_count": int(item.after or "0"),
            }
            for item in diff.changes
        ],
        "from_fingerprint": diff.from_fingerprint,
        "to_fingerprint": diff.to_fingerprint,
        "fingerprints_cover": "allowlisted_category_counts_and_revision_only",
        "rollback_preview": {
            "may_submit_to_product_authority": False,
            "product_apply_required": True,
            "blockers": [item.value for item in preview.blockers],
        },
    }


__all__ = ["compare_product_revisions"]
