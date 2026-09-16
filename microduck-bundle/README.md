# MicroDuck bundle

This isn't wired into the no-duck `isaac-web-playground-core` package. It's
the raw material for whoever integrates it next.

## contents

`isaac-web-playground-engine/` is this project's own MicroDuck implementation,
pulled as-is out of the working `bridge/isaac_playground.py`: the policy
engine (PolicyRunner, clock ownership/take_physics_clock, the ball/arena
props, attach_policy/engage_policy/disengage_policy, the policy_* wire ops).
`policy_engine.py` is a straight extraction, not cleaned up -- it still
references names (ROBOT, CURRENT_ROBOT, TELEOP, the dispatch table) from the
file it was cut out of and needs rewiring against whatever it lands in.
`control.py` is the one part that's already a clean, dependency-free module
(no Isaac/ONNX/NumPy), covered by `test_microduck_control.py`.
`2026-09-07-clock-and-control-fix-report.md` is the full writeup from
tonight's review: what changed, why, and what's still unverified against real
Isaac Sim. Read it before touching the clock-ownership code.

`osrbot-upstream-reference/` is the public MicroDuck-on-Isaac implementation
this project's control constants were checked against tonight (pulled from
github.com/osrbot/microduck-ros2-isaac). Different architecture -- Isaac Lab
SimulationContext + ImplicitActuatorCfg, instead of this project's raw
SingleArticulation + low-level physx.update_simulation() -- but the same
policy contract, and a second working example of it.

## open issue

Engaging the policy calls timeline.pause() to get a precise physics clock.
The MJPEG capture pipeline stops producing frames while the timeline is
paused -- switching to a non-policy robot captures fine, switching to
MicroDuck reliably returns an empty render-product frame. Not fixed yet; the
report above has the evidence trail.
