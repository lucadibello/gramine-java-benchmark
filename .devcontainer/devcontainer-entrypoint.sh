#!/usr/bin/env bash
set -euo pipefail

# start headless nvim watchdog (if you want it always-on)
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

if [ "$DEVUSER" = "root" ]; then
  /usr/local/bin/nvim-server.sh &
  NVIM_SERVER_PID=$!
else
  sudo --preserve-env="$NVIM_ENV_PRESERVE" -u "dev" /usr/local/bin/nvim-server.sh &
  NVIM_SERVER_PID=$!
fi
echo "[entrypoint] nvim server started (pid $NVIM_SERVER_PID)"
