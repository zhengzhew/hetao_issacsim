# Project structure

```text
.
├── bridge/          Isaac Sim Python runtime and robot adapters
├── configs/         Built-in scene/robot catalog and examples
├── deploy/          Windows + WSL deployment wrappers
├── docs/            Architecture, guides, operations and historical notes
├── scripts/         Lifecycle, build and acceptance scripts
├── server/          Node HTTP/API/streaming/agent service
├── src/             Browser streaming SDK helper
├── tests/           Fast host-independent tests
├── tools/           Diagnostics and hardware-side utilities
└── web/             Static browser client
```

The repository is intentionally split by **runtime boundary**, not by language alone. `bridge/` runs in Isaac Sim's Python environment, while `server/` runs in Node/WSL and `web/` runs in the browser. Code should not import across those boundaries; communication goes through the documented TCP/HTTP protocols.

Entry points stay small where practical. Robot-specific policy contracts should live in robot-specific modules rather than accumulating in `bridge/isaac_playground.py`.
