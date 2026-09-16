# Stage 2 catalogs

`scenes.json` and `robots.json` are the runtime library used by both the web server and the Isaac bridge.

- Scene entries point to an Isaac Sim asset path, camera defaults, and a spawn location.
- Robot entries declare an adapter plus the parameters needed by that adapter.
- Stage 2 ships two adapter families: `differential-drive` and `holonomic-drive`.
- Add a new differential robot by adding a catalog entry; browser control code does not change.
- Add a new adapter family by implementing the bridge adapter contract: `info`, `apply_motion`, `stop`, `pose`, `reset`.

The built-in scene paths follow NVIDIA's documented Isaac environment layout. The robot entries use NVIDIA stock assets. Real-server availability is still verified at runtime because installed Isaac asset versions can differ.
