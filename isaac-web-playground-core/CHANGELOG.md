# Changelog

## 0.3.0 - 2026-09-07

### Changed

- Split `bridge/isaac_playground.py` (3335 lines, one file) into `bridge/core/`,
  eleven modules by responsibility, plus a thin entrypoint. See
  `bridge/architecture.md`.
- Removed the MicroDuck policy engine from this build (PolicyRunner, clock
  ownership, the ball/arena props, the `policy_*` wire ops, about 980 lines).
  It's kept as a separate bundle, not deleted.
- Reorganized documentation into architecture, guides, operations and history.
- Moved host IP / WSL username into a git-ignored machine-local deployment
  override.

### Validation note

Isaac Sim isn't available in this packaging environment. Every module parses,
and a whole-file scope check found and fixed three real gaps left by the
split (one function that didn't move, one missing import, one leftover
reference to a removed field). That's as far as this can be verified without
a GPU host; boot it on the real one before it replaces anything running.
