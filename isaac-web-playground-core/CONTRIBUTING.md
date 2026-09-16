# Contributing

## Before opening a change

1. Keep the three runtime boundaries intact: browser, Node service, Isaac bridge.
2. Do not move GPU/physics work into the Node process or network work into the physics loop.
3. Run `npm run check` before committing.
4. When a change affects physics, control rate, latency, or rendering performance, attach a measured before/after result rather than an inferred one.
5. Keep generated files, uploads, logs, credentials, and local runtime state out of Git.

## Code organization

- `server/`: HTTP API, streaming and agent orchestration.
- `bridge/`: code that must execute inside Isaac Sim's Python runtime.
- `web/`: browser-only code.
- `configs/`: versioned built-in scene/robot catalog.
- `scripts/`: lifecycle and acceptance commands.
- `tools/`: diagnostics and one-off operators; production paths must not depend on them.
- `docs/`: architecture, guides, operations and historical notes.
- `tests/`: fast checks that do not require a live Isaac process where possible.

Prefer small modules with explicit inputs over adding another global to a runtime entrypoint.
