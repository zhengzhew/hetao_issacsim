# Validation — Stage 2

## Verified in the build environment

- `npm run check` passes for Node and Python source.
- `npm run stage2:accept:local` passes.
- 4 scenes loaded from the runtime catalog.
- 4 robots loaded from the runtime catalog.
- All 16 Scene × Robot mock combinations switch successfully.
- Differential adapter rejects non-zero lateral motion.
- Holonomic Kaya mock moves laterally through the universal API.
- Carter mock moves forward through the same universal API.
- Watchdog stops stale motion.
- RESET remains functional after multiple session switches.
- Active session query stays consistent.

## Not yet verified in this environment

- Real Isaac Sim loading/switching all four USD scenes.
- Real Carter / Nova Carter / Kaya asset initialization against the server's exact Isaac asset version.
- Real NVIDIA WebRTC video after runtime world switching.
- Real Jetbot movement and real Kaya lateral movement.

These require the user's GPU Isaac server. `npm run stage2:accept` is provided for that validation.
