# Real Server Checklist — Stage 2

```bash
cd isaac-web-playground-stage2
export ISAAC_PUBLIC_IP=<browser-reachable server IP>
# export ISAAC_SIM_DIR=/path/to/isaacsim
npm run preflight
npm run stage2:up
npm run stage2:status
```

Open `http://<server-ip>:8080` in Chrome/Chromium.

Human checks:
- live Isaac video is visible;
- Scene Library and Robot Library open;
- switching Warehouse -> Grid changes the real USD world;
- switching Jetbot -> Kaya changes the real robot;
- Jetbot: W/S/A/D drive, Q/E unavailable;
- Kaya: W/S/A/D drive/turn and Q/E lateral strafe;
- Camera mode controls viewport without moving robot;
- Robot mode does not move the camera;
- STOP and RESET work after several session switches.

Automated real acceptance:

```bash
npm run stage2:accept -- --base http://127.0.0.1:8080
```
