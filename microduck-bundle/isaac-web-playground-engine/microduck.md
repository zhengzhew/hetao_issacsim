# Adding the Pollen MicroDuck

MicroDuck is a 25 cm, ~800 g bipedal robot from Pollen Robotics and Hugging
Face. Every behaviour it ships with — walking, sitting, kicking, roller-skating,
getting back up — is a neural policy trained in MuJoCo and exported to ONNX.
Hardware ships from December 2026; until then everything is simulation.

This is a good fit for the playground for one reason worth stating plainly: it
would be the **first robot here that acts rather than being driven**. Everything
else moves because someone holds a key down.

## Where the asset comes from

[`osrbot/microduck-ros2-isaac`](https://github.com/osrbot/microduck-ros2-isaac)
(Apache-2.0) ships a ready-to-open USD converted from Pollen's MJCF. Nothing
needs converting.

The tutorial has a ROS 2 route and an Isaac Sim route. **We only need the Isaac
Sim route** (its steps 6–8); ROS 2 is step 9 and optional. Nothing here adds a
ROS dependency.

Its root layer agrees with this project on every convention that matters:

```
metersPerUnit = 1
kilogramsPerUnit = 1
upAxis = "Z"
doc = "...validated and post-processed with Isaac Sim 6.0.1"
```

Same units, same up-axis, same Isaac Sim version. It also carries a `Physics`
variant set (`mujoco` / `none` / `physics` / `physx`) already defaulted to
`physx`, which is what Isaac needs.

## Installing it

The asset is a directory — a small `.usda` root plus a `payloads/` folder — so
the HTTP upload endpoint cannot take it; that path accepts one flat file. The
bridge has no such limit: `resolve_upload` walks subdirectories under
`ISAAC_UPLOAD_DIR` and only refuses paths that escape it. So copy the directory
in and register it, with no code change:

```bash
git clone --depth 1 https://github.com/osrbot/microduck-ros2-isaac.git
cp -r microduck-ros2-isaac/assets/isaac/robot_allcollisions "$ISAAC_UPLOAD_DIR/microduck"
```

Then merge [`configs/uploads/microduck.example.json`](../../configs/uploads/microduck.example.json)
into the `catalog.json` in that same directory and restart the bridge.

## The one setting that matters

```json
"fix_root": false
```

Every arm in this project needs its root welded to the world — without it the
base intersects the floor, PhysX emits NaNs, and the Kit process dies. That is
why `fix_root` **defaults to true**.

A biped is the opposite case. It has to stand on its own feet, and it has to be
able to fall over. Welding its root would leave it hovering rigidly, unable to
walk and unable to fail. Getting this wrong does not crash anything — it just
produces a statue, which is harder to diagnose than a crash.

## What is measured and what is guessed

From `contract.py` in the upstream repo — **these are exact**:

| | |
|---|---|
| Joints | 14, named in `POLICY_JOINTS` |
| Home pose | 14 values in `HOME_POSE`, radians |
| Action | 14 joint targets |
| Observation | 61 = 3 base angular velocity + 3 projected gravity + 14×3 (position, velocity, previous action) + 13 command |

These were guesses, and the first load on real hardware (2026-09-03, Isaac Sim
6.0.1) settled part of it:

```
placed /World/WebRobot at (0.000, 0.000, 0.220)
physics tuning applied to 15 body/bodies under /World/WebRobot
drive gains applied to 14 joint(s) (default stiffness=20.0 damping=1.0 max_force=3.0)
robot ready id=microduck adapter=joint-position dofs=14 limits=14
```

**Confirmed:** it loads, the articulation resolves to 14 DOFs matching
`POLICY_JOINTS`, and no `root fixed:` line appears — so `fix_root: false` took
effect. Neither risk below materialised: the payload loaded, and the
four-candidate articulation ladder found `/microduck` on the first try. No PhysX
warnings, no traceback.

**Still not measured:** whether `spawn_z: 0.22` and the gains `20 / 1 / 3` are
*right*, as opposed to merely not fatal. Nothing yet has asked the duck to hold
a pose against gravity, which is the only thing that would tell you.

The two structural risks, recorded because they were real concerns and someone
porting a different robot will meet them:

- The physics variant arrives by **payload**, not reference, and payloads are
  not always loaded automatically. A robot that appears but has no collision or
  gravity is this.
- The articulation root is `/microduck` (the `defaultPrim`), a different shape
  from the arms this adapter was built against.

**Expect it to fall over.** Standing is a learned behaviour here, not a
mechanical property.

## Making it walk

The current integration deliberately matches the released OSRBOT playground at
the policy boundary instead of relying on values that happened to work in an
earlier bridge revision. The pure, testable contract lives in
[`bridge/microduck/control.py`](../../bridge/microduck/control.py).

| Contract item | Current value |
|---|---:|
| Physics / control | 200 Hz / 50 Hz |
| Observation / action | 61 / 14 |
| Velocity command limits | `0.4 / 0.3 / 1.0` |
| Walking action scale | `0.9` |
| Stand/skill action scale | `1.0` |
| Head target low-pass | `0.5` |
| Leg target low-pass | `0.7` |
| Stand/walk switch threshold | `0.05` |

`last_action` and the previous filtered joint target are carried across a hot
policy switch. The earlier bridge reset both values, causing a discontinuity in
the next observation and the next position command.

### Physics clock

The policy still needs exclusive ownership of physics time. `take_physics_clock()`
pauses the timeline and verifies the assumption by lifting the robot 5 cm and
manually stepping twelve 5 ms physics steps. If the robot falls enough, status
reports `clock: "owned"`; otherwise the bridge returns to the legacy shared-clock
behavior and reports `clock: "shared"`.

The bridge currently keeps the existing low-level PhysX stepping path because
that exact path is already wired into the deployed `SingleArticulation` adapter.
The public OSRBOT example instead advances an Isaac `SimulationContext` and
updates its articulation every physics step. If jitter remains after the control
contract fixes above, this stepping/backend difference is the next A/B test --
not something to swap blindly without a real Isaac run.

Use [`microduck-debugging.md`](microduck-debugging.md) for the measured triage
sequence and the fields exposed by `GET /api/policy`.

### Drive gains

This project writes raw USD/PhysX `DriveAPI` gains. The OSRBOT example uses an
Isaac Lab implicit actuator configuration. Their stiffness/damping numbers are
therefore not assumed numerically interchangeable. The existing per-policy raw
gains are retained behind `switch_drive_gains`; turn that option off for an A/B
run if jolts appear specifically at stand/walk transitions.

### Absolute measurements must be repeated

Earlier standing drift and walking-speed numbers were collected while the scene
was still on a shared physics clock. They remain useful only as historical
comparisons within the same run setup. Do not publish or use them as absolute
acceptance values until the same tests have been repeated with
`policy.clock == "owned"` and `timeline_advance_s == 0`.

## Still open

- Verify the owned-clock path on the real Isaac Sim 6.0.1 host.
- Run the stand/walk/gain-switch A/B sequence in `microduck-debugging.md`.
- If filtered targets are smooth but the articulation still chatters, compare
  the low-level PhysX stepper with `SimulationContext.step(render=False)` using
  `tools/probe_policy_runtime.py`.
- The page still needs a general policy-selection control; kick, ball reset and
  camera follow are already separate actions.

## Not to be confused with

- `kabilankb/isaaclab-microduck` — Isaac Lab training environments; a different
  task from this browser playground.
- `jvpflum/microduck-lab` — a MuJoCo RL training workbench.
