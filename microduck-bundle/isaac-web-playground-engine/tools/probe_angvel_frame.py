#!/usr/bin/env python3
"""Is get_angular_velocity() world frame or body frame?

The observation feeds the policy an angular velocity expressed in the robot's
own frame, obtained by rotating the world-frame value by the inverse of the
root orientation. Upstream reads root_ang_vel_w -- the _w says world -- and
rotates it. This project reads SingleArticulation.get_angular_velocity() and
rotates it the same way, on the assumption that it too is world frame.

That assumption has never been checked. If the call already returns a
body-frame value, the rotation is applied twice, and the error vanishes
whenever the robot happens to be upright and facing along +X -- which is
exactly when every test so far has looked at it.

The test: yaw the robot 90 degrees, spin it about the world Z axis, and read
the value back. World frame keeps it on Z. Body frame does not.

    "C:\\isaacsim\\python.bat" tools/probe_angvel_frame.py \
        --usd C:/playground/uploads/microduck/robot_allcollisions.usda
"""

from __future__ import annotations

import argparse
import math

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--usd", required=True)
parser.add_argument("--prim-path", default="/World/Probe")
ARGS = parser.parse_args()

from isaacsim import SimulationApp

kit = SimulationApp(launch_config={"width": 640, "height": 480, "headless": True, "hide_ui": True})

import numpy as np
import omni.timeline
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import add_reference_to_stage, create_new_stage

create_new_stage()
for _ in range(3):
    kit.update()
add_reference_to_stage(usd_path=ARGS.usd, prim_path=ARGS.prim_path)
for _ in range(40):
    kit.update()

timeline = omni.timeline.get_timeline_interface()
timeline.play()
for _ in range(10):
    kit.update()

robot = SingleArticulation(prim_path=ARGS.prim_path, name="probe")
robot.initialize()

# 90 degrees about Z: (w, x, y, z) = (cos45, 0, 0, sin45). The robot's own X
# axis now points along world +Y, so the two frames disagree about everything
# except the Z axis they share.
half = math.sqrt(0.5)
SPIN = np.array([0.0, 0.0, 2.0], dtype=np.float32)      # 2 rad/s about world Z

for label, quat in (("no rotation", np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)),
                    ("yawed 90 deg", np.array([half, 0.0, 0.0, half], dtype=np.float32))):
    robot.set_world_pose(position=np.array([0.0, 0.0, 1.5], dtype=np.float32), orientation=quat)
    robot.set_angular_velocity(SPIN)
    robot.set_linear_velocity(np.zeros(3, dtype=np.float32))
    kit.update()
    read = np.asarray(robot.get_angular_velocity(), dtype=np.float32)
    print(f"  {label:<16} set {SPIN.tolist()} (world Z)  ->  read {read.round(3).tolist()}", flush=True)

print("""
  Both readings on Z  -> the call is WORLD frame, and rotating it is correct.
  Second one off Z    -> it is BODY frame; the rotation in observe() is applied
                         twice, and the policy has been fed a wrong angular
                         velocity whenever the robot was not facing along +X.
""", flush=True)
kit.close()
