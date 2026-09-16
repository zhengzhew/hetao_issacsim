#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs run

find_isaac() {
  if [ -n "${ISAAC_SIM_DIR:-}" ] && [ -x "${ISAAC_SIM_DIR}/python.sh" ]; then printf '%s\n' "$ISAAC_SIM_DIR"; return 0; fi
  for d in "$HOME/isaacsim" "$HOME/isaac-sim" /isaac-sim /opt/isaacsim /opt/isaac-sim; do
    if [ -x "$d/python.sh" ]; then printf '%s\n' "$d"; return 0; fi
  done
  return 1
}
ISAAC_SIM_DIR="$(find_isaac || true)"
if [ -z "$ISAAC_SIM_DIR" ]; then echo "[stage2] Isaac Sim not found. Export ISAAC_SIM_DIR=/path/to/isaacsim" >&2; exit 2; fi

PUBLIC_IP="${ISAAC_PUBLIC_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
if [ -z "$PUBLIC_IP" ]; then echo "[stage2] Could not infer server IP. Export ISAAC_PUBLIC_IP=<browser-reachable IP>." >&2; exit 2; fi
WEB_PORT="${PORT:-8080}"
BRIDGE_PORT="${ISAAC_BRIDGE_PORT:-8765}"
SIGNAL_PORT="${ISAAC_SIGNAL_PORT:-49100}"
MEDIA_PORT="${ISAAC_MEDIA_PORT:-47998}"
DEFAULT_SCENE="${ISAAC_DEFAULT_SCENE:-warehouse}"
DEFAULT_ROBOT="${ISAAC_DEFAULT_ROBOT:-jetbot}"

if [ "${LIVESTREAM:-0}" = "1" ] && [ ! -f web/native-sdk.js ]; then
  echo "[stage2] building NVIDIA native WebRTC client..."
  [ -d node_modules ] || npm install --no-audit --no-fund
  npm run build:native
fi

for name in isaac web; do
  if [ -f "run/$name.pid" ] && kill -0 "$(cat "run/$name.pid")" 2>/dev/null; then echo "[stage2] $name already running pid=$(cat "run/$name.pid")" >&2; exit 2; fi
done

# One switch drives both halves. Starting the bridge without livestream while
# the page is told to use WebRTC leaves a Connect button that can never work.
LIVESTREAM="${LIVESTREAM:-0}"
if [ "$LIVESTREAM" = "1" ]; then
  BRIDGE_LIVESTREAM_FLAG="--livestream"
  WEB_RENDERER="native"
else
  BRIDGE_LIVESTREAM_FLAG="--no-livestream"
  WEB_RENDERER="mjpeg"
fi
UPLOAD_DIR="${ISAAC_UPLOAD_DIR:-$ROOT/uploads}"
mkdir -p "$UPLOAD_DIR"
echo "[stage2] livestream=$LIVESTREAM renderer=$WEB_RENDERER uploads=$UPLOAD_DIR"

export ISAAC_PUBLIC_IP="$PUBLIC_IP" ISAAC_SIGNAL_PORT="$SIGNAL_PORT" ISAAC_MEDIA_PORT="$MEDIA_PORT"
export ISAAC_DEFAULT_SCENE="$DEFAULT_SCENE" ISAAC_DEFAULT_ROBOT="$DEFAULT_ROBOT"

echo "[stage2] starting Isaac Sim default=$DEFAULT_SCENE + $DEFAULT_ROBOT ..."
"$ISAAC_SIM_DIR/python.sh" "$ROOT/bridge/isaac_playground.py" \
  --scene-id "$DEFAULT_SCENE" --robot-id "$DEFAULT_ROBOT" \
  --public-ip "$PUBLIC_IP" --host 127.0.0.1 --port "$BRIDGE_PORT" \
  --signal-port "$SIGNAL_PORT" --stream-port "$MEDIA_PORT" \
  --upload-dir "$UPLOAD_DIR" $BRIDGE_LIVESTREAM_FLAG \
  > "$ROOT/logs/isaac.log" 2>&1 &
ISAAC_PID=$!; echo "$ISAAC_PID" > run/isaac.pid
trap 'kill "$ISAAC_PID" 2>/dev/null || true' ERR

printf '[stage2] waiting for Isaac bridge'
READY=0
for _ in $(seq 1 300); do
  if ! kill -0 "$ISAAC_PID" 2>/dev/null; then echo; tail -n 100 logs/isaac.log >&2 || true; exit 3; fi
  if (echo > "/dev/tcp/127.0.0.1/$BRIDGE_PORT") >/dev/null 2>&1; then READY=1; break; fi
  printf '.'; sleep 1
done
echo
[ "$READY" -eq 1 ] || { echo "[stage2] Isaac bridge not ready" >&2; exit 3; }

echo "[stage2] starting browser playground..."
PORT="$WEB_PORT" ISAAC_STREAM_RENDERER="$WEB_RENDERER" ISAAC_STREAM_HOST="$PUBLIC_IP" \
ISAAC_UPLOAD_DIR="$UPLOAD_DIR" \
ISAAC_SIGNAL_PORT="$SIGNAL_PORT" ISAAC_MEDIA_PORT="$MEDIA_PORT" \
ISAAC_BRIDGE_HOST=127.0.0.1 ISAAC_BRIDGE_PORT="$BRIDGE_PORT" \
ISAAC_DEFAULT_SCENE="$DEFAULT_SCENE" ISAAC_DEFAULT_ROBOT="$DEFAULT_ROBOT" \
node server/index.js > logs/web.log 2>&1 &
WEB_PID=$!; echo "$WEB_PID" > run/web.pid

printf '[stage2] waiting for web'
WEB_READY=0
for _ in $(seq 1 40); do
  if ! kill -0 "$WEB_PID" 2>/dev/null; then echo; tail -n 100 logs/web.log >&2 || true; exit 4; fi
  if command -v curl >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$WEB_PORT/api/catalog" >/dev/null 2>&1; then WEB_READY=1; break; fi
  printf '.'; sleep 1
done
echo
[ "$WEB_READY" -eq 1 ] || { echo "[stage2] Web not ready" >&2; exit 4; }
trap - ERR
cat <<OUT

============================================================
Stage 2 services are up.
Open:                    http://$PUBLIC_IP:$WEB_PORT
Default session:         $DEFAULT_SCENE + $DEFAULT_ROBOT
Scene/Robot library:     use CHANGE SCENE / ROBOT in the browser
Robot keys:              W/S forward, A/D turn, Q/E strafe when supported
Required network:        TCP $WEB_PORT, TCP $SIGNAL_PORT, UDP $MEDIA_PORT
Acceptance:              npm run stage2:accept -- --base http://127.0.0.1:$WEB_PORT
============================================================
OUT
