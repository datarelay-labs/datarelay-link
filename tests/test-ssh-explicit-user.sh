#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$ROOT" <<'PY'
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('allocator', root / 'server/frp-port-allocator.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

base = {
    'id': 'ssh', 'name': 'SSH', 'protocol': 'tcp', 'preset': 'ssh',
    'local_ip': '127.0.0.1', 'local_port': 22,
}
# No service is allowed to carry an SSH login account.  The operator's
# SSH client decides the account, and the allocator never stores the value.
got = mod.normalize_service(base)
assert 'ssh_user' not in got, got
print('SSH_LOGIN_METADATA_NOT_REQUIRED=PASS')

for user in ('deploy.user', 'root', 'ubuntu', 'admin', 'ec2-user',
             'centos', 'root\nx', '\x1broot', 'bad user', 'root\x9b'):
    try:
        mod.normalize_service(dict(base, ssh_user=user))
    except mod.ServiceValidationError:
        pass
    else:
        raise AssertionError('accepted retired ssh_user: %r' % (user,))
print('SSH_LOGIN_METADATA_REJECTED=PASS')
print('SSH_EXPLICIT_USER_TEST=PASS')
PY
