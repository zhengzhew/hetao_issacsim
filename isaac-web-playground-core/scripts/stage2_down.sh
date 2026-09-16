#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
for name in web isaac; do
  f="run/$name.pid"
  if [ -f "$f" ]; then
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then echo "[stage2] stopping $name pid=$pid"; kill "$pid" 2>/dev/null || true; for _ in $(seq 1 15); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done; kill -9 "$pid" 2>/dev/null || true; fi
    rm -f "$f"
  fi
done
echo "[stage2] stopped"
