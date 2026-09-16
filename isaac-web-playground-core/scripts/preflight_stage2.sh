#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0
warn() { printf '[WARN] %s\n' "$*"; }
ok() { printf '[ OK ] %s\n' "$*"; }
bad() { printf '[FAIL] %s\n' "$*"; FAIL=1; }

printf 'Stage 2 preflight\n=================\n'

if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_LINE="$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | head -n 1)"
  [ -n "$GPU_LINE" ] && ok "GPU: $GPU_LINE" || bad "nvidia-smi exists but GPU query failed"
else bad "nvidia-smi not found"; fi

if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  if [ "$NODE_MAJOR" -ge 20 ] 2>/dev/null; then ok "Node $(node --version)"; else bad "Node >=20 required"; fi
else bad "node not found"; fi

find_isaac() {
  if [ -n "${ISAAC_SIM_DIR:-}" ] && [ -x "${ISAAC_SIM_DIR}/python.sh" ]; then printf '%s\n' "$ISAAC_SIM_DIR"; return 0; fi
  for d in "$HOME/isaacsim" "$HOME/isaac-sim" /isaac-sim /opt/isaacsim /opt/isaac-sim; do
    if [ -x "$d/python.sh" ]; then printf '%s\n' "$d"; return 0; fi
  done
  return 1
}
if ISAAC_FOUND="$(find_isaac)"; then ok "Isaac Sim: $ISAAC_FOUND"; else bad "Isaac Sim python.sh not found; export ISAAC_SIM_DIR=/path/to/isaacsim"; fi

for f in configs/scenes.json configs/robots.json; do
  if node -e "JSON.parse(require('fs').readFileSync('$ROOT/$f','utf8'))" >/dev/null 2>&1; then ok "$f valid"; else bad "$f invalid JSON"; fi
done

check_tcp_free() {
  local port="$1"
  if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"; then bad "TCP $port already in use"; else ok "TCP $port available"; fi
}
check_udp_free() {
  local port="$1"
  if command -v ss >/dev/null 2>&1 && ss -lun 2>/dev/null | awk '{print $5}' | grep -Eq "[:.]${port}$"; then warn "UDP $port already appears in use"; else ok "UDP $port available"; fi
}
check_tcp_free "${PORT:-8080}"
check_tcp_free "${ISAAC_SIGNAL_PORT:-49100}"
check_tcp_free "${ISAAC_BRIDGE_PORT:-8765}"
check_udp_free "${ISAAC_MEDIA_PORT:-47998}"

if [ -f "$ROOT/web/native-sdk.js" ]; then ok "Native WebRTC bundle already built"; else warn "web/native-sdk.js missing; stage2_up.sh will build it"; fi

if [ "$FAIL" -eq 0 ]; then printf '\nPREFLIGHT PASS\n'; exit 0; fi
printf '\nPREFLIGHT FAIL\n'; exit 1
