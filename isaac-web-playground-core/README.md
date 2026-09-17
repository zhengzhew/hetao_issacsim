# Isaac Web Playground

Open a web page and drive a live NVIDIA Isaac Sim scene. Nothing to install on
the viewer's machine — no Omniverse, no GPU, no client. One host runs the
simulation; everyone else uses a browser.

## What you get

- **A live view of the simulation**, using native WebRTC with GPU video encoding,
  with MJPEG as a compatibility fallback. Concurrent WebRTC viewers require
  separate capacity and connectivity validation.
- **Manual control** — WASD for the camera, or switch to the robot and drive it.
  Arms get per-joint sliders.
- **Plain-language control** — type "raise the arm and check what it looks
  like"; a model calls the same operations you can and shows you every call it
  makes, including the pictures it takes to check its own work.
- **Your own assets** — upload a USD scene or robot. It is parsed first and
  reports joints, limits and units, so a bad asset fails before it is loaded.
- **Leader/follower teleoperation** — stream joint positions from a physical
  arm on a serial port into the simulated one.

## Requirements

| | |
|---|---|
| Host | one machine with an NVIDIA GPU and **Isaac Sim 6.0.1** |
| Host OS | Native Windows, Windows + WSL2, or Linux |
| Node | 20 or newer |
| Viewer | any browser, any OS, no GPU |

## Running it

Two processes. They talk over TCP 8765.

**1. The bridge**, inside Isaac Sim's Python:

```bash
"$ISAAC_SIM_DIR/python.sh" bridge/isaac_playground.py \
    --host 0.0.0.0 --port 8765 \
    --livestream --hide-ui --no-multi-gpu \
    --upload-dir /path/to/uploads \
    --idle-after 0 --idle-hz 5
```

**2. Build the browser SDK** with `npm ci && npm run build:native`, then start the web server:

```bash
ISAAC_BRIDGE_HOST=<the bridge machine> PORT=8080 node server/index.js
```

Then open `http://<host>:8080`.

For native Windows, follow [the Windows deployment guide](deploy/windows/README-native.md).

On Windows + WSL2 use the wrappers in [`deploy/`](deploy/) instead — they
handle nvm, the WSL↔Windows address split, log rotation and restart-on-crash.
Read [`deploy/README.md`](deploy/README.md) first; the networking there is the
part that most often goes wrong.

## Configuration

Copy `.env.example` to `.env`. The settings that matter:

| Variable | Meaning |
|---|---|
| `ISAAC_BRIDGE_HOST` / `_PORT` | where Isaac Sim is. Under WSL2, **not** `127.0.0.1` |
| `ISAAC_STREAM_RENDERER` | `native` (default, WebRTC) or `mjpeg` (compatibility) |
| `ISAAC_UPLOAD_DIR` | both processes must see this directory, each under its own spelling |
| `ISAAC_TELEOP_WATCHDOG` | seconds before an unattended robot is held still. Default 0.40 |

The language model is optional and reads its credential from `~/gateway.env`,
never from the tree. Without it the page works normally and the chat panel says
so. See [`docs/guides/assistant.md`](docs/guides/assistant.md).

## Layout

```
bridge/isaac_playground.py   entrypoint: process wiring and the main loop
bridge/core/                 the runtime, split by responsibility (see bridge/architecture.md)
server/index.js              Node: MJPEG hub, uploads, HTTP API
server/agent*.js             the plain-language loop and its tools
web/                         browser client; no framework or build step
configs/                     built-in scene/robot catalogue and upload examples
tests/                       host-independent regression tests
deploy/                      Windows + WSL deployment wrappers
tools/                       probes, diagnostics and hardware clients
docs/                        architecture, guides, operations and history
```

## Documentation

| | |
|---|---|
| [`deploy/README.md`](deploy/README.md) | **start here** to run it on real hardware |
| [`docs/operations/compatibility-stream.md`](docs/operations/compatibility-stream.md) | MJPEG compatibility path and historical deployment notes |
| [`docs/guides/uploads.md`](docs/guides/uploads.md) | uploading scenes and robots, and how assets are validated |
| [`docs/guides/teleoperation.md`](docs/guides/teleoperation.md) | leader/follower arm teleoperation |
| [`docs/guides/assistant.md`](docs/guides/assistant.md) | the plain-language control panel |
| [`docs/operations/performance-tuning.md`](docs/operations/performance-tuning.md) | measured GPU cost, and what actually reduces it |
| [`docs/architecture.md`](docs/architecture.md) | how the pieces fit together |
| [`bridge/architecture.md`](bridge/architecture.md) | how the Python bridge is split into modules |

## Measured behaviour

Numbers below are from the current reference deployment unless marked otherwise.

| | |
|---|---|
| Stream | 1280×720, about 25–30 fps with the dual-GPU setup |
| Viewers | 16 max, sharing one capture loop |
| Teleoperation | 22.7 Hz |
| End-to-end latency | about 190 ms on the measured remote/VPN path |
| GPU | dual-GPU rendering is much faster; single-GPU operation frees GPU0 but has measured around 10 fps |

## Known limits

Read these before deciding it fits your use.

- **No authentication.** Anyone who can reach the port can drive the robot.
  This is safe only on a trusted network.
- **One simulation.** Every viewer shares the same scene, robot and camera —
  two people driving at once will fight. This is not a multi-user system.
- **About 190 ms of latency on the measured remote/VPN path**, floored by MJPEG plus the network. Fine for
  demonstration and coarse control; **not** suitable for fine manipulation.
- **The plain-language conversation is shared too.** Two people typing will
  interleave.
- **Uploaded USD is not sandboxed.** The trust model is "trust whoever can
  upload".
- **Real leader-arm hardware has never been exercised** — the serial path is
  written and unit-tested, but no physical arm has been plugged in.

## Licence

Internal NVIDIA project. Isaac Sim assets are subject to NVIDIA's own terms.
