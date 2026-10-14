#!/usr/bin/env python3
"""Verify or atomically select an installed PRIVATE RC41 Link Web candidate.

Only a 0700 development namespace is eligible.  Does not start/stop services,
change Core, publish artifacts, grant permissions, or touch public dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools" / "verify-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("drlink_private_rc41_pin", VERIFIER)
assert spec is not None and spec.loader is not None
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)
SHA = re.compile(r"^[a-f0-9]{64}$")
HEAD = re.compile(r"^[a-f0-9]{40}$")
STATIC = ("index.html", "app.js", "styles.css", "foundation.css", "favicon.svg")
ACTIVE_NAME = "dev-installed-current"


class SelectionError(ValueError):
    """Refuse unsafe, unverifiable, or unapproved private candidate."""


def _within(child: Path, root: Path) -> bool:
    return child != root and root in child.parents


def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise SelectionError("Expected a regular, non-symlink private file")


def _json(path: Path) -> dict:
    _regular(path)
    if path.stat().st_size > 16384:
        raise SelectionError("Unbounded private receipt")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SelectionError("Unreadable private receipt") from exc
    if not isinstance(content, dict):
        raise SelectionError("Private receipt must be an object")
    return content


def _digest(path: Path) -> str:
    _regular(path)
    return pin.digest_file(path)


def verify_development_install(
    private_root: Path, candidate: Path, publisher_receipt: Path
) -> dict:
    if not private_root.is_absolute() or private_root.is_symlink():
        raise SelectionError("Private root must be absolute and non-symlink")
    root = private_root.resolve(strict=True)
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise SelectionError("Private root must be owner-only (0700)")
    if not candidate.is_absolute() or candidate.is_symlink():
        raise SelectionError("Candidate must be absolute and non-symlink")
    installed = candidate.resolve(strict=True)
    if not installed.is_dir() or not _within(installed, root):
        raise SelectionError("Installed Web candidate must be inside private root")
    if not publisher_receipt.is_absolute() or publisher_receipt.is_symlink():
        raise SelectionError("Package receipt must be absolute and non-symlink")
    record = publisher_receipt.resolve(strict=True)
    if not _within(record, root):
        raise SelectionError("Package receipt cannot point outside private root")

    receipt = _json(record)
    head = receipt.get("source_head")
    digest = receipt.get("bundle_sha256")
    if (
        not isinstance(head, str) or not HEAD.fullmatch(head)
        or not isinstance(digest, str) or not SHA.fullmatch(digest)
        or receipt.get("foundation_head") != pin.SOURCE
        or receipt.get("foundation_version") != pin.VERSION
        or receipt.get("foundation_package_count") != len(pin.PACKAGE_SHA256)
        or receipt.get("private_unpublished") is not True
        or receipt.get("publisher_authenticated") is not False
        or receipt.get("live_product_installed") is not False
        or receipt.get("user_e2e_pass") is not False
        or receipt.get("disposable_install") != "PASS"
        or receipt.get("web_suites") != "PASS"
    ):
        raise SelectionError("Private Foundation installation is not pinned and qualified")
    filename = receipt.get("bundle_file")
    if (
        not isinstance(filename, str) or Path(filename).name != filename
        or not filename.endswith(".private.tar.gz")
    ):
        raise SelectionError("Private bundle file name invalid")

    package = record.parent / filename
    if _digest(package) != digest:
        raise SelectionError("Private installable package digest mismatch")
    web = installed / "usr/local/share/drlink-web"
    if web.is_symlink() or not web.is_dir() or not _within(web.resolve(), installed):
        raise SelectionError("Installed Web directory invalid")
    marker = _json(web / "build.json")
    if marker.get("source_head") != head or marker.get("bundle_sha256") != digest:
        raise SelectionError("Installed Web source or archive marker mismatch")

    with tarfile.open(package, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise SelectionError("Duplicate private Web archive member")
        for member in members:
            if (
                not member.name.startswith("data-relay-link-web/")
                or member.name.startswith("/")
                or ".." in Path(member.name).parts
                or not member.isfile() or member.issym() or member.islnk()
            ):
                raise SelectionError("Unsafe private Web package member")
        prefix = "data-relay-link-web/"
        private_count = 0
        for short, expected in pin.PACKAGE_SHA256.items():
            name = (
                prefix + "web/.foundation/packs/datarelay-labs-" +
                short + "-" + pin.VERSION + ".tgz"
            )
            try:
                entry = archive.extractfile(name)
            except KeyError as exc:
                raise SelectionError("Private Foundation package archive is missing") from exc
            if entry is None or hashlib.sha256(entry.read()).hexdigest() != expected:
                raise SelectionError("Private Foundation package archive digest mismatch")
            private_count += 1
        if sum(
            n.startswith(prefix + "web/.foundation/packs/") and n.endswith(".tgz")
            for n in names
        ) != private_count:
            raise SelectionError("Unexpected private npm package in Web bundle")
        for name in STATIC:
            try:
                entry = archive.extractfile(prefix + "web/dist/" + name)
            except KeyError as exc:
                raise SelectionError("Private Web static asset absent") from exc
            if entry is None:
                raise SelectionError("Private Web static asset absent")
            installed_file = web / name
            if _digest(installed_file) != hashlib.sha256(entry.read()).hexdigest():
                raise SelectionError("Private installed Web file differs from package")
    return {
        "link_head": head,
        "foundation_head": pin.SOURCE,
        "foundation_version": pin.VERSION,
        "bundle_sha256": digest,
        "installed_root": str(installed),
        "static_count": len(STATIC),
        "private_package_count": len(pin.PACKAGE_SHA256),
        "public_default_changed": False,
    }


def select_development_candidate(
    private_root: Path, candidate: Path, publisher_receipt: Path, *,
    activate: bool = False, expected_active_name: str | None = None,
) -> dict:
    evidence = verify_development_install(private_root, candidate, publisher_receipt)
    root = private_root.resolve(strict=True)
    installed = Path(evidence["installed_root"])
    active = root / ACTIVE_NAME
    if active.exists() and not active.is_symlink():
        raise SelectionError("Active private version path is not a symlink")
    old_name: str | None = None
    if active.is_symlink():
        # Never follow a pointer that leaves the 0700 private development root.
        current = active.resolve(strict=True)
        if not _within(current, root) or not current.is_dir():
            raise SelectionError("Active private version points outside private root")
        old_name = current.name
    if expected_active_name is not None and old_name != expected_active_name:
        raise SelectionError("Private active version changed since confirmation")
    if activate and old_name != installed.name:
        if old_name is not None and expected_active_name is None:
            raise SelectionError("Expected current private version required for replacement")
        temp = root / (ACTIVE_NAME + ".pending-" + uuid.uuid4().hex)
        try:
            temp.symlink_to(installed.name, target_is_directory=True)
            if temp.resolve(strict=True) != installed:
                raise SelectionError("Private pending version identity mismatch")
            os.replace(temp, active)
        finally:
            temp.unlink(missing_ok=True)
    if activate:
        assert active.resolve(strict=True) == installed
    evidence["active_name"] = old_name if not activate else installed.name
    evidence["is_active"] = evidence["active_name"] == installed.name
    evidence["selection"] = "APPLIED" if activate else "READ_ONLY_VERIFIED"
    return evidence


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-root", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--activate", action="store_true")
    p.add_argument("--expected-active-name")
    args = p.parse_args()
    try:
        result = select_development_candidate(
            args.private_root, args.candidate, args.receipt,
            activate=args.activate, expected_active_name=args.expected_active_name,
        )
    except (SelectionError, OSError, ValueError, tarfile.TarError) as exc:
        print("PRIVATE_RC41_DEV_ACTIVATION=BLOCKED")
        print("REASON=" + str(exc))
        return 1
    print("PRIVATE_RC41_DEV_ACTIVATION=PASS")
    for key, value in result.items():
        print(key.upper() + "=" + str(value))
    print("PUBLIC_LINK_DEPENDENCY_PIN=UNCHANGED")
    print("CUSTOMER_PRODUCTION_RELEASE=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
