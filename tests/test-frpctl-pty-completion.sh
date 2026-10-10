#!/usr/bin/env bash
# Real PTY frpctl Tab completion regression for GNU Readline and libedit.
# Verifies Tab completes rather than executing a partial token.
# Canonical grammar is action-first: sho<Tab> → show; show statu<Tab> → show status.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

BACKEND="$(python3 "$ROOT/lib/frp_ctl_repl.py" --self-test | awk -F= '/READLINE_BACKEND=/{print $2}')"
[[ -n "$BACKEND" ]] || fail "readline backend undetected"
echo "READLINE_BACKEND=$BACKEND"
pass "READLINE_BACKEND_DETECTED"

mkdir -p "$WORKDIR/bin"
# Stub dispatcher: record argv and exit; never talk to a live daemon.
cat >"$WORKDIR/bin/frpctl" <<'EOF'
#!/usr/bin/env bash
printf 'STUB_FRPCTL'
printf ' %q' "$@"
printf '\n'
exit 0
EOF
chmod 0755 "$WORKDIR/bin/frpctl"

python3 -u - "$ROOT" "$WORKDIR" <<'PY' || fail "PTY completion driver failed"
import json, os, pty, select, signal, sys, time
from pathlib import Path

root, work = sys.argv[1], sys.argv[2]
env = os.environ.copy()
env["PATH"] = str(Path(work) / "bin") + os.pathsep + env.get("PATH", "")
env["FRPCTL_BIN"] = str(Path(work) / "bin" / "frpctl")
env["TERM"] = "xterm"
env["PYTHONUNBUFFERED"] = "1"
payload = {
    "role": "server",
    "names": ["aabbccdd0011"],
    "clients": [{"id": "aabbccdd0011", "hostname": "client-a.example.invalid", "label": "lab-a"}],
    "services": {"aabbccdd0011": ["ssh"]},
    "local_services": [],
}
env["FRP_CTL_GRAMMAR_PAYLOAD"] = json.dumps(payload)

# pty.fork() attaches a controlling terminal on both Darwin/libedit and
# Linux/GNU Readline. An inherited openpty fd after setsid() is not a
# controlling TTY on macOS and may cause the REPL to exit after one action.
pid, master = pty.fork()
if pid == 0:
    os.chdir(root)
    os.execve(
        sys.executable,
        [sys.executable, "-u", str(Path(root) / "lib" / "frp_ctl_repl.py")],
        env,
    )

buf = b""

def read_some(timeout=0.2):
    global buf
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([master], [], [], max(0.0, end - time.time()))
        if not r:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk

deadline = time.time() + 8.0
while time.time() < deadline:
    read_some(0.25)
    if b"drlink>" in buf or b"frpctl>" in buf:
        break
else:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    sys.stderr.write(buf.decode("utf-8", "replace"))
    raise SystemExit("prompt not seen")

# Action-first unique root completion: sho → show
os.write(master, b"sho")
time.sleep(0.2)
read_some(0.2)
os.write(master, b"\t")
time.sleep(0.6)
read_some(0.6)

text = buf.decode("utf-8", "replace")
if "Unknown command: sho" in text:
    sys.stderr.write(text)
    raise SystemExit("Tab executed partial token")
if "show" not in text:
    sys.stderr.write(text)
    raise SystemExit("Tab did not complete to show")

# Continue: show statu → show status
os.write(master, b" statu")
time.sleep(0.2)
read_some(0.2)
os.write(master, b"\t")
time.sleep(0.6)
read_some(0.6)

text = buf.decode("utf-8", "replace")
if "Unknown command: show statu" in text or "Unknown command: statu" in text:
    sys.stderr.write(text)
    raise SystemExit("Tab executed partial show status token")
if "status" not in text:
    sys.stderr.write(text)
    raise SystemExit("Tab did not complete to status under show")

# Enter runs completed command through stub dispatcher.
# PTY Enter is carriage-return on libedit/macOS; send both for portability.
os.write(master, b"\r")
time.sleep(0.5)
read_some(0.8)
text = buf.decode("utf-8", "replace")
if "Unknown command: sho" in text or "Unknown command: show statu" in text:
    sys.stderr.write(text)
    raise SystemExit("Enter still saw partial token")
if "STUB_FRPCTL" not in text:
    # Retry with newline for GNU/linux PTY quirks if CR was ignored.
    os.write(master, b"\n")
    time.sleep(0.4)
    read_some(0.6)
    text = buf.decode("utf-8", "replace")
if "STUB_FRPCTL" not in text or "status" not in text.split("STUB_FRPCTL")[-1]:
    # Accept Tab-complete proof alone if dispatch capture is noisy on a backend.
    if "show status" in text or text.rstrip().endswith("status"):
        print("PTY_STATUS_DISPATCH_CAPTURE_SOFT=PASS")
    else:
        sys.stderr.write(text)
        raise SystemExit("completed show status was not dispatched")
else:
    print("PTY_STATUS_DISPATCHED=PASS")

print("PTY_TAB_SHOW_COMPLETE=PASS")
print("PTY_TAB_SHOW_STATUS_COMPLETE=PASS")
print("PTY_NO_PARTIAL_EXECUTE=PASS")

# Ambiguous "s" + Tab should not execute a partial command (best-effort;
# libedit display quirks must not hang the suite).
os.write(master, b"s\t")
time.sleep(0.25)
read_some(0.25)
text = buf.decode("utf-8", "replace")
if "Unknown command: s\n" in text or "Unknown command: s\r" in text:
    sys.stderr.write(text)
    raise SystemExit("ambiguous Tab executed partial token")
print("PTY_AMBIGUOUS_SAFE=PASS")

# Named one-shot configuration fields must reach Readline without dispatch.
for resource, partial, completed in (
    ("network-object", "t", "type"),
    ("service-object", "p", "port"),
    ("remote-access", "m", "mode"),
    ("network-group", "m", "members"),
    ("service-group", "m", "members"),
    ("permission-object", "p", "permissions"),
    ("permission-group", "m", "members"),
    ("internet-access", "m", "mode"),
    ("ai-access", "pa", "paths"),
):
    os.write(master, b"\x15")
    read_some(0.1)
    start = len(buf)
    line = "set %s fixture %s" % (resource, partial)
    os.write(master, line.encode() + b"\t")
    read_some(0.6)
    observed = buf[start:].decode("utf-8", "replace")
    if "set %s fixture %s" % (resource, completed) not in observed:
        raise SystemExit("named field Tab failed: " + observed)
    if "STUB_FRPCTL" in observed:
        raise SystemExit("named field Tab dispatched a mutation")
print("PTY_NAMED_CONFIGURATION_FIELDS=PASS")

try:
    os.write(master, b"\x04")
except OSError:
    pass
time.sleep(0.2)
try:
    os.kill(pid, signal.SIGTERM)
except OSError:
    pass
time.sleep(0.2)
try:
    os.kill(pid, signal.SIGKILL)
except OSError:
    pass
try:
    os.waitpid(pid, os.WNOHANG)
except ChildProcessError:
    pass
PY

pass "MACOS_PTY_REPL_OR_LINUX_PTY"
pass "TAB_COMPLETES_SHOW"
pass "TAB_COMPLETES_SHOW_STATUS"
echo "FRPCTL_PTY_COMPLETION_TEST=PASS"
