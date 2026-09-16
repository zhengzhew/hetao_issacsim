# Deploying on the Windows + WSL box

This is the deployment that actually runs (`10.23.168.172`). Everything here was
previously typed by hand on the machine and existed nowhere else — if the box
were rebuilt, none of it could be reproduced. That is why these files are in the
repo now.

## The shape of it, and why

    Windows desktop session          WSL2
    ┌──────────────────────┐        ┌─────────────────────┐
    │ Isaac Sim + bridge   │◄──TCP──┤ node web server     │
    │ isaac.bat            │  8765  │ web.bat → start-web │
    └──────────┬───────────┘        └──────────┬──────────┘
               │                               │ listens 0.0.0.0:8080
               └── C:\playground\uploads ───────┘   *inside WSL*
                   /mnt/c/playground/uploads
                                               ▲
                                    netsh portproxy from 0.0.0.0:8080

Three facts drive the whole layout, each learned the hard way:

- **Isaac Sim needs a Windows desktop session.** A service or an SSH session has
  no window station, so there is no D3D device and rendering fails. RDP in, or
  redirect the session to the console with `tscon <id> /dest:console`.
- **`127.0.0.1` is not the same host on both sides.** Under WSL2's default NAT
  networking, loopback inside WSL is the WSL VM. The bridge must bind
  `0.0.0.0` and the web server must address it by the gateway address.
- **The page listens inside WSL**, so `http://10.23.168.172:8080` needs a
  `netsh portproxy`. WSL2 forwards only from the Windows loopback.

Enabling mirrored networking (`%USERPROFILE%\.wslconfig` → `[wsl2]` /
`networkingMode=mirrored`, then `wsl --shutdown`) removes the second and third
problems at once, and is worth trying first.

## First install

    C:\playground\                 bridge\, configs\, uploads\, the .bat files
    ~/isaac-web-playground-stage2  server/, web/, tools/, configs/
    ~/start-web.sh                 copy of deploy/wsl/start-web.sh

1. Copy `deploy/windows/*.bat` to `C:\playground\`, and
   `deploy/wsl/start-web.sh` to `~/start-web.sh` in WSL (`chmod +x` it).
2. Copy `bridge/isaac_playground.py` and `configs/` to `C:\playground\`.
3. `mkdir C:\playground\uploads`.
4. In an **Administrator** PowerShell: `deploy\windows\setup-network.ps1`.
5. Start it: `C:\playground\start-all.bat`.
6. Verify: `deploy\windows\preflight.ps1`.

## Every time you update the code

The bridge and the web server live in different places and are updated
separately. Forgetting the first line is the usual mistake.

    # in WSL
    cd ~/isaac-web-playground-stage2
    tar xzf ~/<release>.tar.gz
    cp bridge/isaac_playground.py /mnt/c/playground/bridge/

Restart both windows afterwards. A web-only change (anything under `web/`) needs
only a hard refresh in the browser.

## After a reboot

Isaac Sim needs a desktop session, so somebody has to log in once. Put
`start-all.bat` in the Startup folder, or register it as a Task Scheduler task —
but note that a task set to "run whether the user is logged on or not" runs in
session 0 with no window station, which is exactly the case that does not work.
It has to run in a real desktop session.

Enabling Windows auto-login removes the manual step, at the cost of storing the
password in plaintext in the registry. That is a judgement call for whoever owns
the machine; this box also holds unrelated training data.

## Reading the logs

`isaac.bat` restarts Isaac every 10 s if it exits. If something is wrong at
startup, that means a full Kit boot (~90 s) every 10 s and a very noisy window.
Read the first error after the restart banner, not the last line.

Nothing rotates these logs. If the box runs for days with a restart loop, check
free space on `C:`.

## Known sharp edges

- **The upload directory has two spellings.** `ISAAC_UPLOAD_DIR` in WSL and
  `--upload-dir` on Windows must point at the same place. When they do not,
  uploads report success and then fail to load.
- **`isaac.bat` restarts on the default scene**, not on whatever was selected.
  A restart under a live page silently changes what the user is looking at.
- **WebRTC and the renderer must agree.** `isaac.bat` without `--livestream`
  plus `ISAAC_STREAM_RENDERER=native` gives a Connect button that can never
  work. Change both or neither.
- **The WSL address changes when WSL is rebuilt.** Re-run `setup-network.ps1`.
- **There is no authentication.** Anyone who can reach the port can upload a
  file, switch scenes and drive the robot.
