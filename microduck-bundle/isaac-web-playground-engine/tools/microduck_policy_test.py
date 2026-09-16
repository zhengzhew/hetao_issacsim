#!/usr/bin/env python3
"""Run a MicroDuck ONNX policy on the converted asset, outside the playground.

The point of doing this separately is that two things are being tried at once
-- assembling a 61-dimensional observation correctly, and stepping physics
independently of rendering -- and if they are wired up together the first
failure is indistinguishable from the second. Both fail the same way: the duck
lies on the floor and nothing is logged.

So this proves the policy alone. No web server, no bridge, no streaming; an
empty stage, a ground plane, and the robot.

    "C:\\isaacsim\\python.bat" tools/microduck_policy_test.py \\
        --usd C:/playground/uploads/microduck/robot_allcollisions.usda \\
        --policy C:/playground/policies/alpha_stand.onnx

alpha_stand is the policy to start with: standing is unambiguous. The robot is
either upright or it is not, and no judgement is needed about whether a gait
looks right.
"""

from __future__ import annotations

import argparse
import math
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--usd", required=True)
parser.add_argument("--policy", required=True)
parser.add_argument("--prim-path", default="/World/MicroDuck")
parser.add_argument("--seconds", type=float, default=10.0)
parser.add_argument("--vx", type=float, default=0.0, help="forward command, m/s")
parser.add_argument("--vy", type=float, default=0.0)
parser.add_argument("--yaw-rate", type=float, default=0.0)
parser.add_argument("--action-scale", type=float, default=1.0)
parser.add_argument("--stiffness", type=float, default=0.55)
parser.add_argument("--damping", type=float, default=0.053)
parser.add_argument("--max-force", type=float, default=0.96)
parser.add_argument("--settle", type=float, default=0.5,
                    help="seconds to hold the home pose before the policy takes over")
ARGS = parser.parse_args()

from isaacsim import SimulationApp

kit = SimulationApp(launch_config={
    "width": 1280, "height": 720, "headless": True, "hide_ui": True,
})

import numpy as np
import omni.timeline
import omni.usd
from omni.physx import get_physx_interface
from pxr import Gf, PhysxSchema, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import add_reference_to_stage, create_new_stage

import onnxruntime as ort


# From the upstream contract module. The order is load-bearing: the policy was
# trained against these indices and nothing in the file records them.
POLICY_JOINTS = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)
HOME_POSE = np.array([
    0.0, -0.0873, -0.4579, -0.0049, 0.4530,
    0.3491, 0.3491, 0.0, 0.0,
    0.0, 0.0873, 0.4579, 0.0049, -0.4530,
], dtype=np.float32)

PHYSICS_DT = 1.0 / 200.0
DECIMATION = 4                       # policy runs every 4 physics steps: 50 Hz
CONTROL_DT = PHYSICS_DT * DECIMATION
SPAWN_Z = 0.125                      # where upstream writes the root before stepping


def quat_rotate_inverse(quat_wxyz: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Rotate a world vector into the body frame.

    isaacsim.core reports orientation as (w, x, y, z); Isaac Lab uses
    (x, y, z, w) and upstream's script says so explicitly. Getting this
    backwards produces a plausible-looking observation and a robot that will
    not stand, which is why the startup check below tests it against gravity
    rather than trusting the convention.
    """
    w = quat_wxyz[0]
    q = quat_wxyz[1:]
    a = vector * (2.0 * w * w - 1.0)
    b = np.cross(q, vector) * (2.0 * w)
    c = q * (2.0 * float(np.dot(q, vector)))
    return a - b + c


def set_physics_rate(stage, hz: float) -> None:
    """The policy assumes 200 Hz physics. The default stage is 60."""
    scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    if not scenes:
        scene = UsdPhysics.Scene.Define(stage, "/PhysicsScene")
        prim = scene.GetPrim()
    else:
        prim = scenes[0]
    api = PhysxSchema.PhysxSceneAPI.Apply(prim)
    api.CreateTimeStepsPerSecondAttr().Set(int(hz))
    print(f"  physics rate set to {hz:.0f} Hz on {prim.GetPath()}", flush=True)


def apply_drive_gains(stage, root: str, stiffness: float, damping: float, max_force: float) -> int:
    """An XL330 is a hobby servo; the arm defaults in the playground are 60x this."""
    count = 0
    for prim in Usd.PrimRange(stage.GetPrimAtPath(root)):
        for kind in ("angular", "linear"):
            if not prim.HasAPI(UsdPhysics.DriveAPI, kind):
                continue
            drive = UsdPhysics.DriveAPI.Get(prim, kind)
            drive.CreateStiffnessAttr().Set(stiffness)
            drive.CreateDampingAttr().Set(damping)
            drive.CreateMaxForceAttr().Set(max_force)
            count += 1
    return count



def resolve_write(handle):
    """Pick the joint-target call by construction, as the playground does.

    Isaac's articulation API has moved between releases and this script found
    that out the same way the adapter did: set_joint_position_targets is not
    on SingleArticulation in 6.0.1. Try the candidates in the order that has
    actually worked.
    """
    all_indices = np.arange(len(handle.dof_names), dtype=np.int32)
    try:
        from isaacsim.core.utils.types import ArticulationAction
        if hasattr(handle, "apply_action"):
            def write(values):
                handle.apply_action(ArticulationAction(
                    joint_positions=np.asarray(values, dtype=np.float32),
                    joint_indices=all_indices,
                ))
            return write, "apply_action(ArticulationAction)"
    except Exception:
        pass
    if hasattr(handle, "set_dof_position_targets"):
        def write(values):
            handle.set_dof_position_targets(np.asarray([values], dtype=np.float32))
        return write, "set_dof_position_targets"
    if hasattr(handle, "set_joint_position_targets"):
        def write(values):
            handle.set_joint_position_targets(np.asarray(values, dtype=np.float32))
        return write, "set_joint_position_targets"
    raise SystemExit("no way to command joint targets on this articulation")


print("\n=== stage ===", flush=True)
create_new_stage()
for _ in range(3):
    kit.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

ground = UsdGeom.Xform.Define(stage, "/World/Ground")
plane = UsdGeom.Mesh.Define(stage, "/World/Ground/Plane")
plane.CreatePointsAttr([Gf.Vec3f(-5, -5, 0), Gf.Vec3f(5, -5, 0), Gf.Vec3f(5, 5, 0), Gf.Vec3f(-5, 5, 0)])
plane.CreateFaceVertexCountsAttr([4])
plane.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
UsdPhysics.CollisionAPI.Apply(plane.GetPrim())
# Friction, which upstream sets and this script did not. A bare collider takes
# the default, the feet slip, and the gait covers half the ground it should --
# which reads as a policy that tracks its command badly rather than as a floor
# that is too slippery.
material = UsdShade.Material.Define(stage, "/World/Ground/Material")
physics_material = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
physics_material.CreateStaticFrictionAttr().Set(1.0)
physics_material.CreateDynamicFrictionAttr().Set(1.0)
physics_material.CreateRestitutionAttr().Set(0.0)
binding = UsdShade.MaterialBindingAPI.Apply(plane.GetPrim())
binding.Bind(material, UsdShade.Tokens.weakerThanDescendants, "physics")
light = UsdLux.DomeLight.Define(stage, "/World/Light")
light.CreateIntensityAttr(2000.0)

set_physics_rate(stage, 1.0 / PHYSICS_DT)
add_reference_to_stage(usd_path=ARGS.usd, prim_path=ARGS.prim_path)
for _ in range(40):
    kit.update()

driven = apply_drive_gains(stage, ARGS.prim_path, ARGS.stiffness, ARGS.damping, ARGS.max_force)
print(f"  drive gains on {driven} joint(s): "
      f"stiffness={ARGS.stiffness} damping={ARGS.damping} max_force={ARGS.max_force}", flush=True)

timeline = omni.timeline.get_timeline_interface()
timeline.play()
for _ in range(10):
    kit.update()

robot = SingleArticulation(prim_path=ARGS.prim_path, name="microduck")
robot.initialize()
dof_names = list(robot.dof_names)
print(f"  articulation has {len(dof_names)} DOFs", flush=True)

missing = set(POLICY_JOINTS) - set(dof_names)
if missing:
    raise SystemExit(f"joints the policy needs are not in the articulation: {sorted(missing)}")
# The policy's order is not Isaac's order, and nothing warns about a mismatch.
policy_to_isaac = np.array([dof_names.index(name) for name in POLICY_JOINTS], dtype=np.int64)
print(f"  policy->isaac index map: {policy_to_isaac.tolist()}", flush=True)
write_targets, write_api = resolve_write(robot)
print(f"  joint writes go through {write_api}", flush=True)


print("\n=== policy ===", flush=True)
session = ort.InferenceSession(ARGS.policy, providers=["CPUExecutionProvider"])
net_in = session.get_inputs()[0]
net_out = session.get_outputs()[0]
if net_in.shape[-1] != 61 or net_out.shape[-1] != 14:
    raise SystemExit(f"policy is not 61->14: in={net_in.shape} out={net_out.shape}")
print(f"  {ARGS.policy}: {net_in.name}{net_in.shape} -> {net_out.name}{net_out.shape}", flush=True)


def place_home() -> None:
    """Upright at the spawn height, joints at the home pose, no velocity."""
    robot.set_world_pose(position=np.array([0.0, 0.0, SPAWN_Z]),
                         orientation=np.array([1.0, 0.0, 0.0, 0.0]))
    robot.set_linear_velocity(np.zeros(3))
    robot.set_angular_velocity(np.zeros(3))
    home_isaac = np.zeros(len(dof_names), dtype=np.float32)
    home_isaac[policy_to_isaac] = HOME_POSE
    robot.set_joint_positions(home_isaac)
    robot.set_joint_velocities(np.zeros(len(dof_names), dtype=np.float32))


place_home()
for _ in range(5):
    kit.update()


print("\n=== startup check ===", flush=True)
# The failure this catches: a wrong quaternion convention makes every rotated
# quantity subtly wrong, the observation still looks like 61 plausible numbers,
# and the robot simply never stands. Gravity is known, so check against it.
position, orientation = robot.get_world_pose()
gravity_body = quat_rotate_inverse(np.asarray(orientation, dtype=np.float32),
                                   np.array([0.0, 0.0, -1.0], dtype=np.float32))
print(f"  orientation (as reported) = {np.asarray(orientation).round(4).tolist()}", flush=True)
print(f"  gravity in body frame     = {gravity_body.round(4).tolist()}", flush=True)
if abs(gravity_body[2] + 1.0) > 0.05:
    raise SystemExit(
        "Upright robot does not see gravity as (0, 0, -1) in its own frame. The "
        "quaternion convention is wrong; every rotated term in the observation "
        "would be wrong with it, and the robot would never stand.")
print("  upright robot sees gravity straight down: convention is right", flush=True)


print(f"\n=== running {ARGS.policy.rsplit('/', 1)[-1]} for {ARGS.seconds}s ===", flush=True)
physx = get_physx_interface()
command = np.zeros((1, 13), dtype=np.float32)
command[0, 0:3] = (ARGS.vx, ARGS.vy, ARGS.yaw_rate)
last_action = np.zeros((1, 14), dtype=np.float32)
gravity_world = np.array([0.0, 0.0, -1.0], dtype=np.float32)
sim_clock = 0.0

control_steps = int(ARGS.seconds / CONTROL_DT)
settle_steps = int(ARGS.settle / CONTROL_DT)
render_every = max(1, int(round((1.0 / CONTROL_DT) / 12.0)))    # ~12 fps of rendering
report_every = int(1.0 / CONTROL_DT)

heights: list[float] = []
tilts: list[float] = []
positions: list[tuple[float, float]] = []
start_xy = (0.0, 0.0)
started = time.perf_counter()

for step in range(control_steps):
    position, orientation = robot.get_world_pose()
    orientation = np.asarray(orientation, dtype=np.float32)
    ang_vel_body = quat_rotate_inverse(orientation, np.asarray(robot.get_angular_velocity(), dtype=np.float32))
    gravity_body = quat_rotate_inverse(orientation, gravity_world)
    joint_pos = np.asarray(robot.get_joint_positions(), dtype=np.float32)[policy_to_isaac]
    joint_vel = np.asarray(robot.get_joint_velocities(), dtype=np.float32)[policy_to_isaac]

    observation = np.concatenate((
        ang_vel_body,
        gravity_body,
        joint_pos - HOME_POSE,          # relative to home, not absolute
        joint_vel,
        last_action[0],
        command[0],
    )).astype(np.float32).reshape(1, 61)

    if not np.isfinite(observation).all():
        raise SystemExit(f"observation went non-finite at control step {step}")

    if step < settle_steps:
        # Hold the home pose while PhysX settles the contacts. Feeding a policy
        # a first frame full of impact transients is a good way to make it look
        # broken when it is not.
        target_policy = HOME_POSE.copy()
    else:
        action = session.run([net_out.name], {net_in.name: observation})[0].reshape(14)
        if not np.isfinite(action).all():
            raise SystemExit(f"policy returned non-finite actions at control step {step}")
        last_action[0] = action
        target_policy = HOME_POSE + ARGS.action_scale * action

    target_isaac = np.zeros(len(dof_names), dtype=np.float32)
    target_isaac[policy_to_isaac] = target_policy
    write_targets(target_isaac)

    for _ in range(DECIMATION):
        physx.update_simulation(PHYSICS_DT, sim_clock)
        sim_clock += PHYSICS_DT

    if step % render_every == 0:
        kit.update()

    height = float(position[2])
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(-gravity_body[2])))))
    heights.append(height)
    tilts.append(tilt)
    positions.append((float(position[0]), float(position[1])))
    if step == settle_steps:
        start_xy = (float(position[0]), float(position[1]))

    if step % report_every == 0:
        elapsed = time.perf_counter() - started
        realtime = (step * CONTROL_DT) / max(elapsed, 1e-9)
        moved = math.hypot(position[0] - start_xy[0], position[1] - start_xy[1])
        print(f"  t={step * CONTROL_DT:5.1f}s  height={height * 100:6.2f} cm  "
              f"tilt={tilt:5.1f} deg  moved={moved:5.2f} m  realtime={realtime:.2f}x", flush=True)

elapsed = time.perf_counter() - started


print("\n=== verdict ===", flush=True)
# Ignore the settling phase: it is holding a pose, not running the policy.
tail = slice(settle_steps, None)
final_height = heights[-1]
final_tilt = tilts[-1]
mean_height = float(np.mean(heights[tail]))
print(f"  final height {final_height * 100:.2f} cm, final tilt {final_tilt:.1f} deg", flush=True)
print(f"  mean height  {mean_height * 100:.2f} cm over the policy phase", flush=True)
print(f"  realtime factor {(control_steps * CONTROL_DT) / elapsed:.2f}x "
      f"({elapsed:.1f}s wall for {control_steps * CONTROL_DT:.1f}s simulated)", flush=True)

# Whether it went anywhere. For a walking policy this is the whole question,
# and height and tilt cannot answer it: a robot marching on the spot looks
# exactly like a robot crossing the room.
travelled = math.hypot(positions[-1][0] - start_xy[0], positions[-1][1] - start_xy[1])
policy_seconds = (control_steps - settle_steps) * CONTROL_DT
speed = travelled / max(policy_seconds, 1e-9)
commanded = math.hypot(ARGS.vx, ARGS.vy)
print(f"  travelled    {travelled:.2f} m in {policy_seconds:.1f}s of policy "
      f"= {speed:.3f} m/s (commanded {commanded:.3f})", flush=True)

# 12.5 cm is where it starts; lying down puts the trunk near 5 cm.
if final_height > 0.09 and final_tilt < 35.0 and commanded > 0.01:
    if speed > 0.4 * commanded:
        print(f"  WALKING. Upright and covering {speed:.2f} m/s against a command of "
              f"{commanded:.2f}.", flush=True)
    else:
        print(f"  Upright but going nowhere: {speed:.3f} m/s against a command of", flush=True)
        print(f"  {commanded:.2f}. The gait may be running on the spot -- check that the", flush=True)
        print("  command block reaches the policy and that action_scale is not zero.", flush=True)
elif final_height > 0.09 and final_tilt < 35.0:
    print("  STANDING. The observation, the index map and the stepping are all right.", flush=True)
elif final_height > 0.09:
    print(f"  Upright but leaning {final_tilt:.0f} deg. Physics and observation are", flush=True)
    print("  plausible; the gains or the spawn height are worth a look.", flush=True)
else:
    print("  ON THE FLOOR. Something in the observation, the index map, the gains", flush=True)
    print("  or the stepping is wrong -- and none of them announce themselves.", flush=True)
    print("  The startup check already cleared the quaternion convention, so the", flush=True)
    print("  next things to doubt are the joint order and the drive gains.", flush=True)

kit.close()
