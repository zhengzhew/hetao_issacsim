# Compatibility stream (MJPEG)

## Why

NVIDIA WebRTC carries video over **UDP 47998**. Behind a VPN that NATs the
client (GlobalProtect, address `172.29.x.x`), TCP signalling on 49100 connects
but the UDP media never arrives, so the page sits on "Connecting" forever.
Verified on <host-ip>: the stream works from a browser on the machine
itself and fails from every browser reaching it through the VPN.

## What this adds

The same viewport, rendered server side and pushed as `multipart/x-mixed-replace`
JPEG frames over the HTTP port the page is already served from. Nothing but
that one connection is required, so it works from anywhere the page loads.

|  | WebRTC | Compatibility |
|---|---|---|
| Transport | UDP 47998 + TCP 49100 | the page's own HTTP port |
| Frame rate | 60 | ~12 (configurable) |
| Quality | encoder native | JPEG, 960x540 by default |
| Through a NATing VPN | no | yes |
| Concurrent viewers | one | many, one capture loop feeds all |
| Camera control | native viewport input | A/D orbit, W/S zoom, Q/E height, wheel zoom |
| Robot control | unchanged | unchanged |

## Turning it on

Set the renderer on the web server:

    ISAAC_STREAM_RENDERER=mjpeg

The page then shows a picture with no clicks. With `native` it still tries
WebRTC first and falls back to this automatically when the media does not
arrive. Either way the link under the overlay switches by hand.

## Tuning

| Variable | Default | Notes |
|---|---|---|
| `ISAAC_CAPTURE_WIDTH` / `_HEIGHT` | 960 / 540 | server side render resolution |
| `ISAAC_CAPTURE_FPS` | 12 | capture loop target |
| `ISAAC_CAPTURE_QUALITY` | 60 | JPEG quality, 20-95 |

At the defaults one viewer costs roughly 0.5-1 MB/s. Drop the resolution
before dropping the frame rate; it is the cheaper knob.

## New endpoints

- `GET /api/stream.mjpg` - the multipart stream
- `GET /api/frame.jpg` - one frame, useful for probing
- `GET /api/camera`, `POST /api/camera` - read and set the viewport camera
  (`{"reset": true}` returns to the scene's configured view)

`GET /api/status` gains a `capture` block: connected clients, frames sent, and
the last capture error.

## New bridge ops

`capture_frame`, `get_camera`, `set_camera`, `reset_camera`.

Frames come from a Replicator `rgb` annotator attached to `/OmniverseKit_Persp`,
encoded with Pillow when it is importable inside Kit's Python and with a
zlib PNG encoder otherwise. The render product is released and rebuilt when the
scene changes, since it binds to the stage that was open when it was created.
