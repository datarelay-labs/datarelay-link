#!/usr/bin/env python3
"""Plan narrowly owned, unclaimed Agent installation residue removal.

Never treat a missing executable as proof that a registration is disposable.
A pending transaction, key, committed config, Server state, foreign FRP or
unrecognized content vetoes cleanup. Only the verified fresh installer calls
the apply operation. No installed executable or configuration is sourced.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from drlink_agent_payload import AGENT_LIB_FILES

CA_SCRATCH = re.compile(r"allocator-ca\.crt\.[A-Za-z0-9]{6}\Z")
LIB_FILES = set(AGENT_LIB_FILES) | {
    "runtime-sha256.json", "frpctl", "uninstall-client.sh",
    "com.datarelay.drlink.frpc.plist", "com.datarelay.drlink.lifecycle.plist",
    "drlink-frpc-launch",
}
UNIT_SIGNATURES = {
    "drlink-client.service": ("Data Relay Link Agent", "drlink_frpc_supervisor.py"),
    "drlink-ai-agent.service": ("Data Relay Link AI Agent Worker", "drlink_ai_agent.py"),
    "drlink-lifecycle.service": ("Data Relay Link Agent Lifecycle Worker", "drlink_agent_lifecycle.py"),
}
WRAPPER_MARKERS = {
    "drlink": b"Canonical Data Relay Link operator CLI",
    "frp-client": b"frp-client-common.sh",
    "frpctl": b"Data Relay Link",
    "frp-support-bundle": b"frp_support_bundle.py",
    "frp-update": b"frp-common.sh",
}


class Protected(Exception):
    pass


def inspect(path):
    """Reject symlink components and nonregular objects; no path traversal."""
    if not path.is_absolute() or ".." in path.parts:
        raise Protected()
    for component in reversed(path.parents):
        # macOS system aliases (/var etc.) are not used by the mapped state roots.
        if component.is_symlink():
            raise Protected()
    try:
        st = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode) or not (
        stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)
    ):
        raise Protected()
    return st


def read_file(path):
    st = inspect(path)
    if st is None or not stat.S_ISREG(st.st_mode) or st.st_size > 4 * 1024 * 1024:
        raise Protected()
    return path.read_bytes()


def unit_owned(path):
    try:
        text = read_file(path).decode("utf-8")
    except (UnicodeError, Protected):
        return False
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in ("Description", "ExecStart"):
            if key in fields:
                return False
            fields[key] = value
    if path.name == "frpc.service":
        return (fields.get("Description") in (
            "Data Relay Link Agent", "Data Relay Link Client",
            "Data Relay Link Client (legacy unit name; use drlink-client)",
        ) and fields.get("ExecStart") == "/usr/local/bin/frpc -c /etc/frp/frpc.toml")
    desc, module = UNIT_SIGNATURES[path.name]
    command = fields.get("ExecStart", "")
    return (fields.get("Description") == desc and
            re.fullmatch(r"/[^ ]+/python3 /usr/local/lib/drlink/" + re.escape(module) +
                         (r" worker" if path.name == "drlink-lifecycle.service" else ""), command)
            is not None)


def plan(paths):
    config, etc, state, logs, lib, opt, ca, engine, *rest = map(Path, paths)
    wrappers, units, server_markers = rest[:8], rest[8:12], rest[12:]
    files, dirs, supervisors = set(), set(), []
    # A Server role or foreign FRP must not be affected, even if the Agent
    # config was removed first. Any enrolled or pending state is protected.
    for path in server_markers:
        if os.path.lexists(path):
            raise Protected()

    def add_file(path):
        st = inspect(path)
        if st is None:
            return
        if not stat.S_ISREG(st.st_mode):
            raise Protected()
        files.add(path)

    def scan(path, allow, subdirs=None):
        st = inspect(path)
        if st is None:
            return
        if not stat.S_ISDIR(st.st_mode) or os.path.ismount(path):
            raise Protected()
        for entry in path.iterdir():
            ent = inspect(entry)
            if ent is None:
                raise Protected()
            if stat.S_ISDIR(ent.st_mode):
                if not subdirs or entry.name not in subdirs:
                    raise Protected()
                scan(entry, subdirs[entry.name])
            elif allow(entry):
                add_file(entry)
            else:
                raise Protected()
        dirs.add(path)

    def ca_file(p):
        return p == ca or CA_SCRATCH.fullmatch(p.name) is not None

    def client_version(p):
        # An explicit Agent role is required; legacy/unknown version files
        # are evidence to preserve, not permission to erase.
        data = read_file(p).decode("utf-8")
        if re.search(r"(?m)^ROLE=(client|AgentHost)$", data):
            return True
        # Older POSIX version receipts did not carry ROLE. They are safe
        # only with corroborating Agent-specific payload/unit evidence.
        if re.search(r"(?m)^ROLE=", data):
            return False
        evidence = lib / "frp-client-common.sh"
        return (bool(re.search(r"(?m)^PROJECT_VERSION=[0-9]+\.[0-9]+\.[0-9]+", data))
                and inspect(evidence) is not None
                and b"frp_client_" in read_file(evidence))

    # /etc/frp may be shared by an unrelated installation; retain machine ID.
    # Keep all credentials, committed config, pending state and backups intact.
    if inspect(config) is not None:
        if os.path.ismount(config):
            raise Protected()
        for entry in config.iterdir():
            if entry.name == "client-id":
                if not stat.S_ISREG(inspect(entry).st_mode):
                    raise Protected()
            else:
                raise Protected()
    scan(etc, lambda p: ca_file(p) or (p.name == "version" and client_version(p)))
    scan(state, lambda p: False)
    scan(logs, lambda p: bool(re.fullmatch(r"frpc(?:\.stdout|\.stderr)?\.log(?:\.[0-9]+)?", p.name)))
    scan(opt, lambda p: False)
    scan(lib, lambda p: p.name in LIB_FILES,
         {"__pycache__": lambda p: any(
             p.name.startswith(name[:-3] + ".") and p.name.endswith(".pyc")
             for name in AGENT_LIB_FILES if name.endswith(".py"))})

    if any(p.parent == lib for p in files):
        evidence = lib / "frp-client-common.sh"
        if evidence not in files or b"frp_client_" not in read_file(evidence):
            raise Protected()

    for path in wrappers:
        if inspect(path) is not None:
            if WRAPPER_MARKERS[path.name] not in read_file(path):
                raise Protected()
            add_file(path)
    for path in units:
        if inspect(path) is not None:
            if not unit_owned(path):
                raise Protected()
            # Drop-ins may redefine the service; do not decide ownership from
            # the unit file alone if a drop-in exists.
            if inspect(path.with_name(path.name + ".d")) is not None:
                raise Protected()
            add_file(path)
            supervisors.append(path.name)
    if inspect(engine) is not None:
        # frpc is not a product-specific executable name. Require a known
        # product supervisor and an Agent-specific runtime file as corroboration.
        if not supervisors or lib / "frp-client-common.sh" not in files:
            raise Protected()
        add_file(engine)

    # Empty config trees are safe to prune, but never remove client-id.
    if inspect(config) is not None and not any(config.iterdir()):
        dirs.add(config)
    if not files and not dirs:
        return None
    return {
        "files": sorted(str(p) for p in files),
        "dirs": sorted((str(p) for p in dirs), key=lambda p: (-len(Path(p).parts), p)),
        "units": sorted(supervisors),
        "identities": {
            str(p): [p.lstat().st_dev, p.lstat().st_ino, p.lstat().st_mode]
            for p in files | dirs
        },
    }


def apply(paths, expected, sandbox):
    current = plan(paths)
    if current != expected:
        raise Protected()
    if not sandbox:
        # A live service is not an orphan. Do not stop it automatically.
        # Confirm the actual loaded fragment and overrides before disabling
        # an inactive product unit; never modify a foreign unit.
        for unit in current["units"]:
            loaded = subprocess.run(
                ["systemctl", "show", unit, "-p", "FragmentPath", "-p", "DropInPaths", "-p", "ActiveState"],
                capture_output=True, text=True, check=True,
            )
            properties = dict(line.split("=", 1) for line in loaded.stdout.splitlines() if "=" in line)
            fragment = properties.get("FragmentPath", "")
            if (fragment not in current["files"] or
                    properties.get("DropInPaths") or
                    properties.get("ActiveState") not in ("inactive", "failed")):
                raise Protected()
        for unit in current["units"]:
            subprocess.run(["systemctl", "disable", unit], check=True)
        # Refuse a standalone frpc process rather than killing a process
        # whose ownership could have changed.
        engine = paths[7]
        for proc in Path("/proc").glob("[0-9]*/exe"):
            try:
                if os.readlink(proc) in (engine, engine + " (deleted)"):
                    raise Protected()
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
    if plan(paths) != expected:
        raise Protected()
    for name in current["files"]:
        path = Path(name)
        # Keep the old CA until the caller installs the verified replacement
        # atomically. A failed cleanup must not silently lose the trust anchor.
        if name == paths[6]:
            continue
        st = inspect(path)
        if (st is None or not stat.S_ISREG(st.st_mode) or
                [st.st_dev, st.st_ino, st.st_mode] != current["identities"][name]):
            raise Protected()
        path.unlink()
    for name in current["dirs"]:
        path = Path(name)
        st = inspect(path)
        if st is not None:
            if path == Path(paths[6]).parent and Path(paths[6]).exists():
                continue
            path.rmdir()
    if current["units"] and not sandbox:
        subprocess.run(["systemctl", "daemon-reload"], check=True)


def main():
    action, sandbox, *paths = sys.argv[1:]
    try:
        if action == "plan":
            result = plan(paths)
            print(json.dumps(result, separators=(",", ":")) if result else "")
        elif action == "apply":
            expected = json.loads(sys.stdin.read())
            apply(paths, expected, sandbox == "1")
        else:
            return 2
    except (Protected, OSError, ValueError, subprocess.CalledProcessError):
        if action == "plan":
            return 0  # protected/unknown: ordinary enrollment/repair rules apply
        print("ERROR: Agent residue cleanup could not safely complete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
