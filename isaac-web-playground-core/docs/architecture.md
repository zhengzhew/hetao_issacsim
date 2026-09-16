# Stage 2 Architecture

```text
Browser Playground
  |-- Scene Library ----\
  |-- Robot Library -----+--> POST /api/session/launch
  |-- Camera / Robot UI -/             |
  |                                     v
  |                              Isaac Bridge
  |                                     |
  |                  +------------------+------------------+
  |                  |                                     |
  |             Scene Loader                         Robot Adapter
  |                  |                         +-----------+-----------+
  |                  v                         |                       |
  |              USD Stage             DifferentialDrive       HolonomicDrive
  |                                      Jetbot/Carter/Nova          Kaya
  |
  +-- Native WebRTC <--------- same long-lived Isaac Sim process
  |
  +-- Universal motion(linear, lateral, angular) --------------------->
```

Stage 2 owns one active scene/robot combination. It does not create per-user Isaac processes.
