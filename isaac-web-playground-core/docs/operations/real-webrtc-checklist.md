# Real WebRTC Checklist — Stage 2

Stage 2 keeps one long-lived Isaac Sim / WebRTC process while the active USD stage and robot adapter are switched at runtime.

Expected native path:

```text
Browser <video>
  -> @nvidia/ov-web-rtc
  -> TCP 49100 signaling
  -> UDP 47998 media
  -> same Isaac Sim process
  -> current USD scene + current robot
```

Checks:
1. Native SDK bundle exists: `web/native-sdk.js`.
2. Browser can reach server TCP 49100.
3. Browser can receive UDP 47998.
4. Initial live video appears.
5. Open Scene/Robot Library and launch a different combination.
6. The stream should remain in the same page; a short freeze during USD loading is acceptable.
7. After launch, the video must show the new world/robot and controls must target the new adapter.
8. If video does not recover, inspect `logs/isaac.log`, public IP, firewall and NVENC availability.

The web page itself is served separately on TCP 8080 (or `PORT`). There is no iframe viewer service in Stage 2.
