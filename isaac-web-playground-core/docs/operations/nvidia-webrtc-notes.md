# NVIDIA WebRTC notes

This project embeds NVIDIA Omniverse WebRTC directly in the Playground page through `@nvidia/ov-web-rtc`.

Runtime boundary:
- Playground HTTP: default TCP 8080
- Isaac WebRTC signaling: default TCP 49100
- Isaac WebRTC media: default UDP 47998
- Local control bridge: default TCP 8765 (kept server-local in normal deployment)

Stage 2 switches USD worlds and robot adapters inside the same Isaac Sim process. The browser WebRTC surface therefore stays owned by the Playground; it does not load a separate viewer iframe for each scene.

Build the browser bundle on the server with:

```bash
npm install
npm run build:native
```

The local `npm run demo` mode does not require the NVIDIA SDK bundle because it renders its own mock canvas.
