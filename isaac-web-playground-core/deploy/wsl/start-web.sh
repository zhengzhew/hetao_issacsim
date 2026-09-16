#!/bin/bash
# Runs inside WSL. Invoked by deploy/windows/web.bat.
#
# `bash -lc` does not load nvm, so node has to be brought in explicitly. That is
# the whole reason this file exists rather than calling node from the .bat.
set -u

# A machine-local credential file, kept out of the repo and out of the process
# list. Optional: without it the page still works, the chat panel just says
# there is no model.
[ -f "$HOME/gateway.env" ] && . "$HOME/gateway.env"

export NVM_DIR="$HOME/.nvm"
# shellcheck source=/dev/null
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

cd "${PLAYGROUND_DIR:-$HOME/isaac-web-playground-stage2}" || exit 1

export PORT="${PORT:-8080}"
# native only if isaac.bat is also started with --livestream; the two must agree
# or the page offers a Connect button that can never work.
export ISAAC_STREAM_RENDERER="${ISAAC_STREAM_RENDERER:-mjpeg}"
export ISAAC_STREAM_HOST="${ISAAC_STREAM_HOST:-127.0.0.1}"
export ISAAC_SIGNAL_PORT="${ISAAC_SIGNAL_PORT:-49100}"
export ISAAC_MEDIA_PORT="${ISAAC_MEDIA_PORT:-47998}"

# The bridge runs on Windows. Under WSL2's default NAT networking, 127.0.0.1
# from in here is the WSL VM, not Windows, so it must be addressed explicitly.
# With mirrored networking localhost does work; the gateway address is the
# portable choice, and an explicit ISAAC_BRIDGE_HOST always wins.
if [ -z "${ISAAC_BRIDGE_HOST:-}" ]; then
  gateway="$(ip route show default 2>/dev/null | awk '{print $3; exit}')"
  export ISAAC_BRIDGE_HOST="${gateway:-127.0.0.1}"
fi
export ISAAC_BRIDGE_PORT="${ISAAC_BRIDGE_PORT:-8765}"

# Both processes must see the same directory, each under its own spelling.
# Get this wrong and uploads appear to succeed while the simulator reports
# "uploaded asset not found".
export ISAAC_UPLOAD_DIR="${ISAAC_UPLOAD_DIR:-/mnt/c/playground/uploads}"
mkdir -p "$ISAAC_UPLOAD_DIR" 2>/dev/null || true

# The assistant reaches Claude through NVIDIA's OpenAI-compatible gateway, not
# the Anthropic API. The credential already exists for claude-code-router on
# this machine, so read it from there rather than keeping a second copy --
# one place to rotate.
if [ -z "${GATEWAY_API_KEY:-}" ] && [ -f "$HOME/.claude-code-router/config.json" ]; then
  eval "$(python3 - "$HOME/.claude-code-router/config.json" <<'PYEOF'
import json, shlex, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
for provider in data.get("Providers", data.get("providers", [])) or []:
    url, key = provider.get("api_base_url"), provider.get("api_key")
    models = provider.get("models") or []
    if url and key:
        print(f"export GATEWAY_BASE_URL={shlex.quote(url)}")
        print(f"export GATEWAY_API_KEY={shlex.quote(key)}")
        if models:
            print(f"export GATEWAY_MODEL={shlex.quote(str(models[0]))}")
        break
PYEOF
)"
fi
export GATEWAY_MODEL="${GATEWAY_MODEL:-azure/anthropic/claude-sonnet-5}"

echo "[web] port=$PORT renderer=$ISAAC_STREAM_RENDERER"
if [ -n "${GATEWAY_API_KEY:-}" ]; then
  echo "[web] assistant=$GATEWAY_MODEL via ${GATEWAY_BASE_URL%%\?*}"
else
  echo "[web] assistant=off (no GATEWAY_API_KEY; the chat panel will say so)"
fi
echo "[web] bridge=$ISAAC_BRIDGE_HOST:$ISAAC_BRIDGE_PORT"
echo "[web] uploads=$ISAAC_UPLOAD_DIR"

if ! (echo > "/dev/tcp/$ISAAC_BRIDGE_HOST/$ISAAC_BRIDGE_PORT") >/dev/null 2>&1; then
  echo "[web] WARNING: cannot reach the bridge at $ISAAC_BRIDGE_HOST:$ISAAC_BRIDGE_PORT."
  echo "[web]          The page will load but show OFFLINE and no picture."
  echo "[web]          Check that isaac.bat is running with --host 0.0.0.0 and that"
  echo "[web]          Windows Firewall allows inbound TCP $ISAAC_BRIDGE_PORT."
fi

exec node server/index.js
