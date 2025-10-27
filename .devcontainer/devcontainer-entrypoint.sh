#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${DEVCONTAINER_USER:-${REMOTE_USER:-dev}}"
if ! id -u "${REMOTE_USER}" >/dev/null 2>&1; then
  echo "[entrypoint] remote user '${REMOTE_USER}' not found; defaulting to root"
  REMOTE_USER="root"
fi

# Provision a watchdog that keeps a headless Neovim server running for remote editing
cat >/usr/local/bin/nvim-server.sh <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
SOCK="${NVIM_LISTEN_ADDRESS:-/tmp/nvim.sock}"
mkdir -p "$(dirname "$SOCK")"
while :; do
  rm -f "$SOCK" || true
  nvim --headless --listen "$SOCK" || true
  sleep 1
done
EOS
chmod +x /usr/local/bin/nvim-server.sh

NVIM_ENV_PRESERVE="NVIM_LISTEN_ADDRESS"
if [ -n "${SSH_AUTH_SOCK:-}" ]; then
  NVIM_ENV_PRESERVE="${NVIM_ENV_PRESERVE},SSH_AUTH_SOCK"
fi

NVIM_SERVER_PID=""
if ! pgrep -u "${REMOTE_USER}" -f 'nvim --headless --listen' >/dev/null 2>&1; then
  if [ "${REMOTE_USER}" = "root" ]; then
    /usr/local/bin/nvim-server.sh &
    NVIM_SERVER_PID=$!
  else
    sudo --preserve-env="${NVIM_ENV_PRESERVE}" -u "${REMOTE_USER}" /usr/local/bin/nvim-server.sh &
    NVIM_SERVER_PID=$!
  fi
  echo "[entrypoint] nvim server started (pid ${NVIM_SERVER_PID})"
else
  echo "[entrypoint] nvim server already running; skipping"
fi

# Launch OpenSSH daemon in the foreground to keep container alive
echo "[entrypoint] starting sshd on port 2222"
/usr/sbin/sshd -D &
SSHD_PID=$!

cleanup() {
  if [ -n "${NVIM_SERVER_PID:-}" ] && ps -p "${NVIM_SERVER_PID}" >/dev/null 2>&1; then
    kill "${NVIM_SERVER_PID}" || true
  fi
  if [ -n "${SSHD_PID:-}" ] && ps -p "${SSHD_PID}" >/dev/null 2>&1; then
    kill "${SSHD_PID}" || true
  fi
}
trap cleanup EXIT

wait "${SSHD_PID}"
