#!/usr/bin/env bash
# Exercise actual runner syntax blocks against isolated Git fixtures.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$ROOT/tests" "$@" <<'PY'
import os
import pathlib
import subprocess
import sys
import tempfile

suite = pathlib.Path(sys.argv[1])
# Git hooks and callers may export repository/index paths. Every fixture child
# must stay inside its temporary repository, independent of that caller state.
fixture_environment = {
    key: value for key, value in os.environ.items()
    if not key.startswith("GIT_") and key not in ("BASH_ENV", "ENV")
}
fixture_environment.update(
    GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
    GIT_TERMINAL_PROMPT="0", LC_ALL="C",
)
all_tools = (
    "frp-server-status", "frp-project-update", "frp-update",
    "frp-upstream", "frp-client", "frpctl",
)
# Preserve each runner's scope: fast PR checks tracked shell files only;
# full and portability also inspect untracked scripts and named entrypoints.
runners = (
    ("full", "run-all.sh", 'echo "=== shell syntax ==="',
     'echo "=== Python compile ==="', all_tools, True),
    ("fast", "run-fast-pr.sh", 'echo "=== shell syntax ==="',
     'echo "=== Python compile ==="', (), False),
    ("portability", "run-portability-container.sh", "while IFS= read -r -d '' f; do",
     './tests/test-portability.sh',
     ("frp-server-status", "frp-update", "frp-client", "frpctl"), True),
)
valid = "#!/usr/bin/env bash\nprintf executed > .syntax-executed\n"
invalid = "#!/usr/bin/env bash\nif then\n"
failures = []
cases = []


def check_case(checks, name, broken=None, tracked=True, empty_shell_inventory=False, edge_names=False):
    cases.append(name)
    with tempfile.TemporaryDirectory(prefix="shell-syntax-fixture-") as tmp:
        root = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q", str(root)], check=True, env=fixture_environment)
        (root / "tools").mkdir()
        for tool in all_tools:
            (root / "tools" / tool).write_text(valid)
        if not empty_shell_inventory:
            filenames = ["00-first.sh", "later-valid.sh"]
            if edge_names:
                filenames.extend(["later valid.sh", "line\nbreak.sh", "-leading.sh"])
            for filename in filenames:
                (root / filename).write_text(valid)
        subprocess.run(["git", "add", "--all"], cwd=root, check=True, env=fixture_environment)
        if not empty_shell_inventory:
            (root / "00-first-untracked.sh").write_text(valid)
        if broken is not None:
            (root / broken).write_text(invalid)
            if tracked:
                subprocess.run(["git", "add", "--", broken], cwd=root, check=True, env=fixture_environment)
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", checks], cwd=root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            timeout=15, env=fixture_environment,
        )
        expected_success = broken is None
        matched = result.returncode == 0 if expected_success else (
            result.returncode != 0 and "syntax error" in result.stderr
        )
        if (root / ".syntax-executed").exists():
            matched = False
            print("FAIL %s: syntax-check target was executed" % name)
        if not matched:
            failures.append(name)
            print("FAIL %s: rc=%s, expected %s" % (
                name, result.returncode, "success" if expected_success else "syntax failure"))
            print(result.stderr[-2000:])
        else:
            print("PASS %s" % name)


for name, filename, start_marker, end_marker, tools, includes_untracked in runners:
    runner = (suite / filename).read_text()
    start = runner.index(start_marker)
    end = runner.index(end_marker, start)
    # Exclude only this regression's own invocation to avoid recursion.
    checks = "\n".join(line for line in runner[start:end].splitlines()
                       if line.strip() != './tests/test-shell-syntax-enumeration.sh')
    check_case(checks, name + "_filename_safe_valid_inventory", edge_names=True)
    check_case(checks, name + "_empty_shell_inventory", empty_shell_inventory=True)
    check_case(checks, name + "_later_tracked_shell", "zz-later-invalid.sh")
    if includes_untracked:
        check_case(checks, name + "_later_untracked_shell", "zz-later-untracked-invalid.sh", tracked=False)
    for tool in tools:
        check_case(checks, name + "_extensionless_" + tool, "tools/" + tool)
if failures:
    raise SystemExit("SHELL_SYNTAX_ENUMERATION=FAIL (%s)" % ", ".join(failures))
# Re-run the same real fixture checks with an explicitly unrelated caller Git
# context. Only this small self-test is suppressed in the child; all runner
# cases execute again. The unrelated index/config must remain byte-for-byte.
if "--fixture-isolation-child" not in sys.argv[2:]:
    with tempfile.TemporaryDirectory(prefix="shell-syntax-caller-") as tmp:
        caller = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q", str(caller)],
                       check=True, env=fixture_environment)
        (caller / "sentinel.txt").write_text("preserve caller repository\n")
        subprocess.run(["git", "add", "--", "sentinel.txt"], cwd=caller,
                       check=True, env=fixture_environment)
        watched = (caller / ".git/index", caller / ".git/config")
        before = {path: path.read_bytes() for path in watched}
        polluted = dict(fixture_environment,
                        GIT_DIR=str(caller / ".git"),
                        GIT_COMMON_DIR=str(caller / ".git"),
                        GIT_WORK_TREE=str(caller),
                        GIT_INDEX_FILE=str(caller / ".git/index"))
        child = subprocess.run(
            ["bash", str(suite / "test-shell-syntax-enumeration.sh"),
             "--fixture-isolation-child"], cwd=caller, env=polluted,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=60,
        )
        if child.returncode or any(path.read_bytes() != before[path] for path in watched):
            print(child.stdout[-2000:])
            print(child.stderr[-2000:])
            raise SystemExit("SHELL_SYNTAX_ENUMERATION=FAIL (caller Git isolation)")
        print("PASS inherited_git_environment_isolation (caller index/config unchanged)")
print("SHELL_SYNTAX_ENUMERATION=PASS (%s isolated runner cases)" % len(cases))
PY
