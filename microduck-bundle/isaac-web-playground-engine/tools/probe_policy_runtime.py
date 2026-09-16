#!/usr/bin/env python3
"""Find out whether this Isaac Sim can step physics faster than it renders.

A locomotion policy is trained at a fixed control rate -- MicroDuck's is 50 Hz
over 200 Hz physics -- and a policy fed at the wrong rate falls over. The
playground's main loop currently calls kit.update() once per iteration, which
steps physics and renders together, so control happens at the render rate:
about 12 Hz here, 5 Hz once idle throttling engages.

Decoupling the two is the whole job. This script establishes, by running it
rather than by reading documentation, which of the available mechanisms exists
on this build and how fast it actually is.

Run it with Isaac Sim's own Python:

    "$ISAAC_SIM_DIR/python.bat" tools/probe_policy_runtime.py \
        --usd C:/playground/uploads/microduck/robot_allcollisions.usda

It loads the robot so the numbers are measured against a real 14-DOF
articulation rather than an empty stage.
"""

from __future__ import annotations

import argparse
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scene", default=None, help="scene USD to open first, so the render cost is realistic")
parser.add_argument("--usd", required=True, help="robot USD to load, so the measurement is realistic")
parser.add_argument("--prim-path", default="/World/ProbeRobot")
parser.add_argument("--seconds", type=float, default=3.0, help="how long to measure each mode")
ARGS = parser.parse_args()

from isaacsim import SimulationApp

kit = SimulationApp(launch_config={
    "width": 1280, "height": 720, "headless": True, "hide_ui": True,
})

import omni.timeline
import omni.usd
from isaacsim.core.utils.stage import add_reference_to_stage, create_new_stage


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'YES' if ok else 'no '}  {name:<52} {detail}", flush=True)


print("\n=== what is importable ===", flush=True)

try:
    import onnxruntime as ort
    report("onnxruntime", True, f"{ort.__version__}, providers={ort.get_available_providers()}")
except Exception as exc:
    report("onnxruntime", False, f"{type(exc).__name__}: {exc}")

SimulationContext = None
try:
    from isaacsim.core.api import SimulationContext as _SC
    SimulationContext = _SC
    report("isaacsim.core.api.SimulationContext", True, "")
except Exception as exc:
    report("isaacsim.core.api.SimulationContext", False, f"{type(exc).__name__}: {exc}")

physx = None
try:
    from omni.physx import get_physx_interface
    physx = get_physx_interface()
    report("omni.physx.get_physx_interface", True,
           f"update_simulation={hasattr(physx, 'update_simulation')}")
except Exception as exc:
    report("omni.physx.get_physx_interface", False, f"{type(exc).__name__}: {exc}")


print("\n=== stage ===", flush=True)
if ARGS.scene:
    # Render cost dominates the budget and depends entirely on the scene. An
    # empty stage flatters the numbers; measure against what actually runs.
    from isaacsim.core.utils.stage import open_stage
    open_stage(ARGS.scene)
    for _ in range(60):
        kit.update()
else:
    create_new_stage()
    for _ in range(3):
        kit.update()
add_reference_to_stage(usd_path=ARGS.usd, prim_path=ARGS.prim_path)
for _ in range(30):
    kit.update()

stage = omni.usd.get_context().get_stage()
print(f"  loaded {ARGS.usd}", flush=True)

# The authored physics rate is what "one step" means below. Isaac defaults to
# 60 Hz; MicroDuck's policy expects 200 Hz, so this is the number that has to
# change and the one that decides how many substeps a rendered frame needs.
try:
    from pxr import PhysxSchema, UsdPhysics
    scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    if scenes:
        px = PhysxSchema.PhysxSceneAPI.Apply(scenes[0])
        rate = px.GetTimeStepsPerSecondAttr().Get()
        print(f"  physics scene {scenes[0].GetPath()} timeStepsPerSecond = {rate}", flush=True)
    else:
        print("  no UsdPhysics.Scene on this stage", flush=True)
except Exception as exc:
    print(f"  could not read the physics rate: {type(exc).__name__}: {exc}", flush=True)

timeline = omni.timeline.get_timeline_interface()
timeline.play()
for _ in range(10):
    kit.update()


def measure(label: str, step, seconds: float) -> float:
    """Steps as fast as it can for `seconds`, and reports the rate."""
    count = 0
    started = time.perf_counter()
    while time.perf_counter() - started < seconds:
        step()
        count += 1
    elapsed = time.perf_counter() - started
    rate = count / elapsed
    print(f"  {label:<44} {rate:8.1f} steps/s   ({count} in {elapsed:.2f}s)", flush=True)
    return rate


print(f"\n=== rates, {ARGS.seconds}s each ===", flush=True)

baseline = measure("kit.update()  (physics + render)", kit.update, ARGS.seconds)

physx_rate = None
if physx is not None and hasattr(physx, "update_simulation"):
    # The question this answers: can physics advance without paying for a
    # frame? If yes, the main loop can run control at 50 Hz and render at 12.
    now = [0.0]

    def physx_step() -> None:
        physx.update_simulation(1.0 / 200.0, now[0])
        now[0] += 1.0 / 200.0

    physx_rate = measure("physx.update_simulation  (physics only)", physx_step, ARGS.seconds)

sim_rate = None
if SimulationContext is not None:
    try:
        sim = SimulationContext(physics_dt=1.0 / 200.0, rendering_dt=1.0 / 200.0)
        sim.initialize_physics()
        sim_rate = measure("SimulationContext.step(render=False)",
                           lambda: sim.step(render=False), ARGS.seconds)
    except Exception as exc:
        report("SimulationContext.step(render=False)", False, f"{type(exc).__name__}: {exc}")


# Who actually advances physics. The simulation clock is the wrong thing to
# watch: a call can step PhysX without moving the timeline, and a call can move
# the timeline without the robot going anywhere. The observable that cannot lie
# is whether the robot falls, so drop it and measure how far.
print("\n=== who actually steps physics (measured by dropping the robot) ===", flush=True)

DROP_FROM = 0.60
STEPS = 100


def make_handle():
    from isaacsim.core.prims import SingleArticulation
    handle = SingleArticulation(prim_path=ARGS.prim_path, name="probe")
    handle.initialize()
    return handle


def drop_and_measure(label: str, action, handle) -> None:
    """Put the robot in the air, run the mechanism, report how far it fell."""
    import numpy as np
    handle.set_world_pose(position=np.array([0.0, 0.0, DROP_FROM]))
    handle.set_linear_velocity(np.zeros(3))
    for _ in range(2):
        kit.update()
    before = float(handle.get_world_pose()[0][2])
    started = time.perf_counter()
    for _ in range(STEPS):
        action()
    elapsed = time.perf_counter() - started
    after = float(handle.get_world_pose()[0][2])
    fell = before - after
    # 100 steps of 5 ms is 0.5 s; free fall over that is about 1.2 m, so
    # anything above a few centimetres means physics genuinely advanced.
    verdict = "PHYSICS MOVED" if fell > 0.02 else "nothing happened"
    print(f"  {label:<44} fell {fell * 100:6.2f} cm in {elapsed:5.2f}s wall   {verdict}", flush=True)


try:
    handle = make_handle()
    timeline.play()
    for _ in range(10):
        kit.update()

    drop_and_measure("kit.update(), timeline playing", kit.update, handle)

    if physx is not None and hasattr(physx, "update_simulation"):
        clock = [0.0]

        def manual() -> None:
            physx.update_simulation(1.0 / 200.0, clock[0])
            clock[0] += 1.0 / 200.0

        drop_and_measure("physx.update_simulation", manual, handle)

    if SimulationContext is not None:
        try:
            sc = SimulationContext.instance() or SimulationContext(physics_dt=1.0 / 200.0)
            sc.initialize_physics()
            drop_and_measure("SimulationContext.step(render=False)",
                             lambda: sc.step(render=False), handle)
        except Exception as exc:
            print(f"  SimulationContext.step failed: {type(exc).__name__}: {exc}", flush=True)
except Exception as exc:
    print(f"  could not bind the robot for the drop test: {type(exc).__name__}: {exc}", flush=True)


# Dividing one rate by the other would be wrong: each measurement above had the
# machine to itself. What matters is whether both fit in the same second, so run
# the pattern the real loop would use and see what comes out.
print("\n=== the two together, which is the actual question ===", flush=True)

SUBSTEPS = 16          # 200 Hz physics against a ~12 fps render
if physx is not None and hasattr(physx, "update_simulation"):
    now = [0.0]
    frames = 0
    steps = 0
    started = time.perf_counter()
    while time.perf_counter() - started < ARGS.seconds:
        for _ in range(SUBSTEPS):
            physx.update_simulation(1.0 / 200.0, now[0])
            now[0] += 1.0 / 200.0
            steps += 1
        kit.update()
        frames += 1
    elapsed = time.perf_counter() - started
    physics_hz = steps / elapsed
    render_fps = frames / elapsed
    control_hz = physics_hz / 4.0        # the policy runs every 4 physics steps
    print(f"  {SUBSTEPS} physics steps per rendered frame:", flush=True)
    print(f"    physics {physics_hz:7.1f} Hz   (200 needed)", flush=True)
    print(f"    control {control_hz:7.1f} Hz   (50 needed)", flush=True)
    print(f"    render  {render_fps:7.1f} fps  (12.4 is the current stream rate)", flush=True)
    print(f"    realtime factor {physics_hz / 200.0:.2f}x", flush=True)

    print("\n=== verdict ===", flush=True)
    if physics_hz >= 190:
        print(f"  Real time holds: physics {physics_hz:.0f} Hz, control {control_hz:.0f} Hz,", flush=True)
        print(f"  and the stream still gets {render_fps:.1f} fps. The loop can be", flush=True)
        print("  restructured as planned.", flush=True)
    else:
        slow = 200.0 / max(physics_hz, 1e-9)
        print(f"  Physics only reaches {physics_hz:.0f} Hz when a frame is rendered", flush=True)
        print(f"  alongside it, so the robot would walk {slow:.1f}x slower than real", flush=True)
        print("  time. Either the render rate comes down or the stream does.", flush=True)
        budget_fps = (1.0 - 200.0 * (1.0 / max(physx_rate, 1e-9))) / max(1.0 / max(baseline, 1e-9), 1e-9)
        print(f"  Rendering would have to drop to roughly {max(budget_fps, 0.0):.1f} fps to", flush=True)
        print("  leave 200 Hz of physics inside one second.", flush=True)
else:
    print("\n=== verdict ===", flush=True)
    print("  No physics-only stepping worked; control cannot be decoupled this way.", flush=True)

kit.close()
