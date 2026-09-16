# MicroDuck jitter debugging

Use this when the robot visibly shakes, chatters at the joints, or jolts when it
switches between standing and walking. The goal is to separate **policy-output
jitter** from **physics/actuator jitter** instead of changing parameters until
it looks better.

## Known-good control contract

The integration keeps the public MicroDuck runtime/playground contract in
`bridge/microduck/control.py` and checks it without launching Isaac Sim:

```bash
python3 tools/check_microduck_config.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

The important values are:

- physics: 200 Hz; policy inference every 4 physics steps (50 Hz);
- velocity envelope: `vx ±0.4`, `vy ±0.3`, `yaw ±1.0`;
- `alpha_walking.onnx`: action scale `0.9`;
- skill/stand policies: action scale `1.0`;
- target low-pass: head/neck `0.5`, legs `0.7`;
- stand/walk switch threshold: command-vector norm `0.05`.

The bridge also preserves `last_action` and the previous filtered target across
hot policy changes. Clearing either value inserts an artificial discontinuity
into the next 61-D observation or the next joint command.

## Runtime triage

With MicroDuck engaged:

```bash
curl -s http://<host>:8080/api/policy
```

Inspect these fields:

- `clock`: must preferably be `owned`. `shared` means the renderer/timeline can
  still advance the same PhysX scene in addition to the policy loop.
- `timeline_advance_s`: should stay at zero on an owned clock.
- `dropped_seconds`: should stay near zero. Growth means the main loop cannot
  keep the requested 200 Hz wall-clock pace.
- `control_metrics.raw_target_delta_max_rad`: how hard the network target moves
  on the current control tick.
- `control_metrics.filtered_target_delta_max_rad` and
  `filtered_target_delta_rms_rad`: what is actually sent after low-pass.
- `control_metrics.joint_velocity_*`: how violently the simulated articulation
  is moving now.

Interpretation:

1. **Raw delta large, filtered delta much smaller, robot looks better** — the
   missing target low-pass was a major cause.
2. **Filtered delta small but joint velocity remains noisy** — do not tune the
   network first; investigate stepping, DriveAPI gains, contacts and the
   articulation backend.
3. **Only policy transitions jolt** — compare with `switch_drive_gains=false`.
   Dynamic DriveAPI gain changes are a playground compatibility mechanism, not
   part of the released policy contract.
4. **`clock=shared`** — treat all absolute speed/drift measurements as invalid
   until the clock path is fixed. Two clocks can also make motion look harsher
   because the policy does not own all physics steps.

## A/B sequence on the real Isaac host

Run one variable at a time and keep the same scene/camera:

1. Stand policy for 20 s, no command.
2. Walking policy, `vx=0.30`, `vy=0`, `yaw=0`, for 10 s.
3. Toggle W on/off ten times to exercise stand/walk switching.
4. Repeat step 3 with `switch_drive_gains=false`.
5. Only if jitter remains with smooth targets and an owned clock, compare the
   current low-level PhysX stepper with `SimulationContext.step(render=False)`
   using `tools/probe_policy_runtime.py` before changing production code.

Record the `/api/policy` JSON at the start and end of each run. That gives an
objective trace instead of a visual judgement alone.

## What not to do

- Do not restore browser commands above the policy's runtime envelope just
  because the UI slider permits them.
- Do not set walking action scale back to `1.0` unless the policy itself was
  trained/exported for that scale.
- Do not copy Isaac Lab `ImplicitActuator` stiffness values directly into raw
  USD `DriveAPI` and assume the numeric meaning is equivalent.
- Do not accept a `realtime ~= 1.0` number as proof of correct timing when the
  clock is `shared`; that metric only counts steps taken by this module.
