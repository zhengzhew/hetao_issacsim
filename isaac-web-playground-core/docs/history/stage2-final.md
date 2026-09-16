# Stage 2 Definition of Done

Stage 2 goal: convert the fixed Web Isaac demo into a configurable single-session playground.

## Required capabilities

1. Scene Library with multiple USD choices.
2. Robot Library with multiple robots.
3. Browser selection and runtime Launch.
4. One universal motion contract independent of robot model.
5. At least two meaningfully different adapter families.
6. Capability-aware input controls.
7. Runtime scene/robot switching preserves WebRTC/control infrastructure.
8. Stage 1 safety: heartbeat watchdog, STOP and RESET.

## Implemented

- 4 scene profiles.
- 4 robot profiles.
- 16 selectable combinations.
- DifferentialDriveAdapter: Jetbot, Carter v1, Nova Carter.
- HolonomicDriveAdapter: Kaya.
- Universal `motion(linear, lateral, angular)` API.
- W/S forward/back, A/D yaw, Q/E lateral when supported.
- `GET /api/catalog`, `GET /api/session`, `POST /api/session/launch`.
- Same interface in local Mock and real Isaac bridge.
- Automated local acceptance for all 16 combinations.
- Automated real-server acceptance script for representative real profiles and motion.

## Stage 2 acceptance rule

**Local PASS** means the product/control architecture is complete and regression-tested without Isaac.

**Real PASS** additionally requires the GPU server to successfully load/switch the real USD assets and prove real Jetbot forward motion plus real Kaya lateral motion through the same web API.
