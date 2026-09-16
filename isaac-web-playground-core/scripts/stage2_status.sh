#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"; PORT="${PORT:-8080}"
echo "Processes"
for name in isaac web; do f="run/$name.pid"; if [ -f "$f" ]; then pid="$(cat "$f")"; if kill -0 "$pid" 2>/dev/null; then echo "  $name: UP pid=$pid"; else echo "  $name: DOWN stale-pid=$pid"; fi; else echo "  $name: DOWN"; fi; done
if command -v curl >/dev/null 2>&1; then
  printf '\nCatalog\n'; curl -fsS "http://127.0.0.1:$PORT/api/catalog" 2>/dev/null || echo "  unavailable"
  printf '\n\nSession\n'; curl -fsS "http://127.0.0.1:$PORT/api/session" 2>/dev/null || echo "  unavailable"
  printf '\n\nStatus\n'; curl -fsS "http://127.0.0.1:$PORT/api/status" 2>/dev/null || echo "  unavailable"
  printf '\n'
fi
printf '\nLast Isaac log lines\n'; tail -n 25 logs/isaac.log 2>/dev/null || true
