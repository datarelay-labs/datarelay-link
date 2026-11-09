#!/usr/bin/env bash
set -euo pipefail
if [[ "$(id -un)" != "aella" ]]; then
  echo 'ERROR: install as aella, the existing Codex user' >&2
  exit 2
fi
run_dir=/home/aella/drlink-validation/codex-e2e-supervised-20261105
src="$(cd "$(dirname "$0")" && pwd)/e2e_codex_watchdog.py"
user_unit="$HOME/.config/systemd/user/drlink-codex-e2e.service"
if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then export XDG_RUNTIME_DIR="/run/user/$(id -u)"; fi
test -f "$run_dir/SCENARIO_TRACKER.tsv"
test -r "$src"
test -s "$run_dir/codex_session_id.txt" || {
  echo "ERROR: pin the exact resumable Codex session in $run_dir/codex_session_id.txt" >&2
  exit 2
}
mkdir -p "$HOME/.config/systemd/user"
install -m 0755 "$src" "$run_dir/e2e_codex_watchdog.py"
cat > "$run_dir/supervisor.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/python3 /home/aella/drlink-validation/codex-e2e-supervised-20261105/e2e_codex_watchdog.py \
  watch --run-dir /home/aella/drlink-validation/codex-e2e-supervised-20261105 \
  --tmux-target codex:0.0 --interval-seconds 60 --cooldown-seconds 900 \
  --max-attempts 2 --allow-relaunch
EOF
chmod 0755 "$run_dir/supervisor.sh"
systemctl --user stop drlink-codex-e2e.service || true
cat > "$user_unit" <<'EOF'
[Unit]
Description=DataRelay Link CLI-only E2E Codex watchdog (existing session only)
After=default.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=/home/aella/datarelay-link-main
ExecStart=/bin/bash /home/aella/drlink-validation/codex-e2e-supervised-20261105/supervisor.sh
Environment=HOME=/home/aella
Environment=PATH=/home/aella/.nvm/versions/node/v22.23.2/bin:/home/aella/.local/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user reset-failed drlink-codex-e2e.service || true
systemctl --user enable --now drlink-codex-e2e.service
systemctl --user is-active drlink-codex-e2e.service
/usr/bin/python3 "$run_dir/e2e_codex_watchdog.py" status
