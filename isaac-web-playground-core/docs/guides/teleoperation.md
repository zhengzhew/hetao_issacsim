# Leader / follower teleoperation

## The shape of it

The leader arm is physical hardware on a serial port, so it cannot live inside
Isaac Sim. Three pieces:

    leader arm --serial--> so101_leader.py --HTTP--> playground --TCP--> Isaac Sim
    (your desk)            (wherever the arm is)     (web server)        (follower)

`tools/so101_leader.py` runs on whatever machine the arm is plugged into. It
needs only the Python standard library, and talks to the playground on the same
port the web page uses — so the arm can sit on your desk while the simulation
runs in the server room. It does **not** have to run on the Isaac Sim machine.

## Running it

    # no hardware yet: drive the follower with a generated trajectory
    python3 tools/so101_leader.py --server http://<host-ip>:8080 --simulate

    # real SO-101 leader (needs lerobot installed on that machine)
    python3 tools/so101_leader.py --server http://<host-ip>:8080 --port /dev/ttyACM0

Load an arm in the playground first — teleop is refused unless the active robot
is joint driven.

## Joint names and units — read this before plugging in hardware

The calibration map is keyed by **follower** joint name, with `source` naming
the **leader** joint. Getting that backwards produces a session where every
sample is rejected, so the client no longer guesses: it engages first, asks the
follower for its joint names, and builds the map against those.

If nothing matches it says so and exits rather than streaming into the void:

    [leader] no leader joint maps onto a follower joint.
             Follower has: Rotation, Pitch, ...; leader reports: shoulder_pan, ...
             Map them with --map follower=leader,... and try again.

    python3 so101_leader.py --port /dev/ttyACM0 \
        --map Rotation=shoulder_pan,Pitch=shoulder_lift,Jaw=gripper

`--unit rad|deg|raw` converts what the leader reports. lerobot does not report
radians, so **`--unit rad` on real hardware will drive the follower into its
limits**. Check what your leader actually returns before trusting the default.

## Calibration

By default the script zeroes the follower at whatever pose the leader is in
when it starts, then streams from there. Sending raw servo counts straight at a
follower is how you slam an arm into its limit on the very first sample, so raw
pass-through is opt-in (`--no-zero`).

Each joint maps as `follower = scale * (raw - offset)`, optionally inverted:

    {"calibration": {"Rotation": {"source": "Rotation", "offset": 100.0,
                                  "scale": 0.01, "invert": true}}}

Capture one and reuse it:

    python3 tools/so101_leader.py --port /dev/ttyACM0 --write-calibration leader.json
    python3 tools/so101_leader.py --port /dev/ttyACM0 --calibration leader.json

With no calibration, joints pass through by name and anything the follower does
not have is dropped.

## Safety

- **Slew limited.** No joint moves more than `--teleop-max-step` (0.08 rad by
  default) per sample, so the first sample after engage ramps toward the leader
  instead of jumping there from wherever the arm happens to be.
- **One leader at a time.** Engaging mints a token; samples must carry it. A
  killed leader's in-flight samples cannot move the arm or wedge the next
  leader's sequence numbers, and an old leader exiting cannot stop the new one.
- **Sliders and `/api/robot/joints` are refused while a leader is engaged**, so
  a second tab cannot fight the stream.
- **A calibration belongs to its session.** It is cleared on disengage and on
  relaunch, so the next operator never inherits someone else's offsets.
- **Hold, never drop.** If the leader stops sending for `ISAAC_TELEOP_HOLD`
  seconds (0.5 by default) the follower holds its last pose. It is not zeroed —
  an arm commanded to zero falls.
- **Stale samples are discarded** by sequence number, so a sample that overtakes
  another on a lossy link cannot rewind the arm.
- **Relaunching a scene or robot drops the teleop session**, because the
  follower it was driving no longer exists.
- **The page can cut the leader loose** at any time with *Disengage leader*.
- While a leader is driving, the joint sliders become a read-only readout.

## Rate and latency — measured, not guessed

Rate and lag are separate problems and they were fixed separately.

The client sends over **several connections at once** (`--connections`, default
4) and holds **one slot** for the newest pose rather than a queue. A queue was
tried and made things worse: buffered samples add their wait to the control lag,
which is the one thing teleoperation cannot afford. With a single slot, a pose
nobody has picked up is simply overwritten by a fresher one.

Measured from a Mac to the Windows box over the corporate VPN, simulated leader
at 30 Hz:

| Configuration | Applied rate | Lag |
|---|---|---|
| 1 connection | 7 Hz | 178 ms |
| 4 connections + queue | 15-17 Hz | 270 ms |
| **4 connections, single slot** | **20 Hz** | **184 ms** |
| 8 connections, single slot | 22 Hz | 202 ms |

Eight connections buy 2 Hz and cost 18 ms and a lot of superseded samples; four
is the setting.

Where the 184 ms goes, from the same measurements:

- **~90 ms** is the VPN round trip. `curl` on a reused connection to
  `/api/config`, which touches nothing, measures 78-115 ms.
- **~40 ms** is the bridge path. `/api/teleop/status` on a reused connection
  measures 103-165 ms, and the bridge itself reports 0.2 ms of work — the rest
  is waiting for the Kit main loop, which is single threaded and runs every op
  including rendering.
- the remainder is slot wait and jitter.

**So: remote teleoperation over this VPN has a floor of roughly 150 ms.** At
20-30 Hz the motion is continuous rather than stepping, but it is visibly behind
the hand. Fine for demonstrating the pipeline; poor for precise work.

**The only way to get low latency is to run the leader client on the machine
running Isaac Sim** — loopback is 0.6 ms mean. That means the physical arm
plugged into that box, with a person next to it. Watching the simulation can be
remote; precise teleoperation cannot. These are different use cases and it is
worth being explicit about which one is being asked for.

Samples are rate limited twice: `ISAAC_TELEOP_MAX_HZ` (120/s) across everything,
and `ISAAC_TELEOP_MAX_HZ_PER_SOURCE` (80/s) per peer, so one misbehaving client
cannot spend the whole budget and starve the real leader.

## Endpoints

`POST /api/teleop/engage` · `POST /api/teleop` (one sample) ·
`POST /api/teleop/disengage` · `POST /api/teleop/calibrate` ·
`GET /api/teleop/status`

The token that `engage` returns is a capability: samples, calibration changes
and a targeted disengage all require it. `GET /api/teleop/status` is public and
therefore reports only `has_token`, never the token itself. A disengage with no
token always works — it is the operator's stop control.

## Not done

- No authentication. Anyone who can reach the port can engage a leader and move
  the arm. Same trade-off as the rest of the tool, but the consequence is larger
  here.
- Single follower. A second leader that engages takes over from the first, which
  is then cleanly locked out — but there is no queue or arbitration.
- The leader's own pose is not drawn in the scene. You see the follower only.
- The real-hardware path (`--port`) has never been run against an actual SO-101.
  The simulated leader has been exercised end to end against real Isaac Sim:
  arm loaded, joints driven, watchdog hold verified.
