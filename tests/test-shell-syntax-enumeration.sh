#!/usr/bin/env bash
# Execute the actual runner syntax checks against isolated Git fixtures.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$ROOT/tests/run-all.sh" <<'PY'
import pathlib
import subprocess
import sys
import tempfile

runner = pathlib.Path(sys.argv[1]).read_text()
start = runner.index('echo "=== shell syntax ==="')
end = runner.index('./tests/test-shell-syntax-enumeration.sh', start)
checks = runner[start:end]
tools = (
    "frp-server-status", "frp-project-update", "frp-update",
    "frp-upstream", "frp-client", "frpctl",
)
valid = "#!/usr/bin/env bash\nprintf 'ok\\n'\n"
invalid = "#!/usr/bin/env bash\nif then\n"
failures = []


def check_case(name, broken=None, tracked=True, empty_shell_inventory=False):
    with tempfile.TemporaryDirectory(prefix="shell-syntax-fixture-") as tmp:
        root = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "tools").mkdir()
        for tool in tools:
            (root / "tools" / tool).write_text(valid)
        if not empty_shell_inventory:
            for filename in ("00-first.sh", "later valid.sh", "line\nbreak.sh", "-leading.sh"):
                (root / filename).write_text(valid)
        subprocess.run(["git", "add", "--all"], cwd=root, check=True)
        if not empty_shell_inventory:
            (root / "00-first-untracked.sh").write_text(valid)
        if broken is not None:
            (root / broken).write_text(invalid)
            if tracked:
                subprocess.run(["git", "add", "--", broken], cwd=root, check=True)
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", checks], cwd=root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            timeout=15,
        )
        expected_success = broken is None
        if (result.returncode == 0) != expected_success:
            failures.append(name)
            print("FAIL %s: rc=%s, expected %s" % (
                name, result.returncode, "success" if expected_success else "syntax failure"))
            print(result.stderr[-2000:])
        else:
            print("PASS %s" % name)


check_case("filename_safe_valid_inventory")
check_case("empty_shell_inventory", empty_shell_inventory=True)
check_case("later_tracked_shell", "zz-later-invalid.sh")
check_case("later_untracked_shell", "zz-later-untracked-invalid.sh", tracked=False)
for tool in tools:
    check_case("extensionless_" + tool, "tools/" + tool)
if failures:
    raise SystemExit("SHELL_SYNTAX_ENUMERATION=FAIL (%s)" % ", ".join(failures))
print("SHELL_SYNTAX_ENUMERATION=PASS (10 isolated runner cases)")
PY
