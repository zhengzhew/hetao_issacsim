# bridge/ layout

`isaac_playground.py` was one 3335-line file. Now it's a thin entrypoint (process
wiring and the main loop, nothing else) plus `core/`, split by responsibility.

    core/app_context.py   CLI args, boots the Isaac SimulationApp
    core/catalog.py       built-in scene/robot JSON catalogs + user uploads
    core/scene.py         loading a USD stage, scene-level camera placement
    core/uploads.py       validating and inspecting an uploaded USD asset
    core/adapters.py      RobotAdapter and one class per drive type
    core/session.py       the currently loaded scene + robot, launch_session()
    core/streaming.py     MJPEG frame capture, pointing the camera at what loaded
    core/teleop.py        leader/follower arm teleoperation
    core/activity.py      slows the main loop when nobody is watching or moving
    core/net.py           dispatch() op table, request queue, TCP handler/server
    core/compat.py        one function so adapters.py can ask if a policy add-on
                           is driving the robot, without depending on one

app_context has to be imported first: it's the one module that touches
omni.*/isaacsim.* at module scope, because it's the one that boots the
SimulationApp. Everything else does its Isaac imports inside function bodies,
same as the original file did, so this is the only real ordering constraint.

## shared state

A few values get reassigned after other modules already imported them --
which scene/robot is loaded, the catalog after a reload, teleop's last-motion
watchdog. `from .session import CURRENT_SCENE` would snapshot whatever
CURRENT_SCENE was at import time and never see launch_session() change it
again, so those modules do `from . import session` and read `session.CURRENT_SCENE`
at the point of use instead. Functions and classes don't have this problem
(they're not reassigned after definition) and are imported by name as usual.

## putting a policy-driven robot back

MicroDuck's policy engine came out of this build (PolicyRunner, clock
ownership, the ball/arena props, attach_policy/engage_policy/disengage_policy,
the policy_* wire ops, about 980 lines). `core/compat.duck_policy_driven()` is
the one hook left in adapters.py for reporting policy state; wiring the
policy_* ops back into net.dispatch() and the advance_policy() call into the
main loop is the rest of it. The extracted engine code and the upstream
reference it was checked against are in the separate MicroDuck bundle.

## what's checked and what isn't

Every file parses. A whole-file scope check (imports, defs, function params,
loop/comprehension/except/with targets) ran across every module afterward and
found three real gaps on the first pass -- a function that didn't get moved, a
missing import, one leftover reference to a field that no longer exists -- all
fixed, second pass clean.

What that doesn't cover: this hasn't booted against a real Isaac Sim process.
The split kept every function body byte for byte from the working file, moved
whole, not retyped, which is the safest way to do this without a GPU host to
test on. Smoke-test it on the real host before it replaces anything running.
