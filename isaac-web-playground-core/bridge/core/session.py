"""Current session state: which scene + robot is loaded, and how it got there."""
from __future__ import annotations

from .app_context import time, traceback
from . import catalog
from .adapters import (RobotAdapter, DifferentialDriveAdapter, HolonomicDriveAdapter, JointPositionAdapter)
from .scene import load_scene, set_camera
from .streaming import camera_defaults, frame_robot
from .teleop import TELEOP, set_teleop_calibration

ADAPTERS = {
    "differential-drive": DifferentialDriveAdapter,
    "holonomic-drive": HolonomicDriveAdapter,
    "joint-position": JointPositionAdapter,
}

ROBOT: RobotAdapter = RobotAdapter()
ROBOT_ERROR: str | None = None
CURRENT_SCENE: dict | None = None
CURRENT_ROBOT: dict | None = None
CURRENT_SCENE_URL = ""
SESSION = {
    "status": "starting",
    "sceneId": None,
    "robotId": None,
    "launchId": 0,
    "launchedAt": None,
    "error": None,
}
LAST_MOTION = {"linear": 0.0, "lateral": 0.0, "angular": 0.0, "source": "none"}
LAST_MOTION_AT = 0.0
WATCHDOG_STOPPED = True


def robot_info() -> dict:
    info = ROBOT.info()
    if ROBOT_ERROR:
        info = {**info, "configured": True, "ready": False, "error": ROBOT_ERROR}
    return info


def session_info() -> dict:
    return {
        **SESSION,
        "scene": CURRENT_SCENE,
        "robot": robot_info(),
        "sceneUrl": CURRENT_SCENE_URL,
    }


def launch_session(scene_id: str, robot_id: str) -> dict:
    global ROBOT, ROBOT_ERROR, CURRENT_SCENE, CURRENT_ROBOT, CURRENT_SCENE_URL
    global SESSION, LAST_MOTION, LAST_MOTION_AT, WATCHDOG_STOPPED

    if scene_id not in catalog.SCENE_BY_ID:
        raise ValueError(f"unknown scene id: {scene_id}")
    if robot_id not in catalog.ROBOT_BY_ID:
        raise ValueError(f"unknown robot id: {robot_id}")
    scene = catalog.SCENE_BY_ID[scene_id]
    robot_cfg = catalog.ROBOT_BY_ID[robot_id]
    adapter_cls = ADAPTERS.get(robot_cfg.get("adapter"))
    if adapter_cls is None:
        raise ValueError(f"unsupported robot adapter: {robot_cfg.get('adapter')}")

    SESSION = {
        "status": "launching",
        "sceneId": scene_id,
        "robotId": robot_id,
        "launchId": int(SESSION.get("launchId") or 0) + 1,
        "launchedAt": None,
        "error": None,
    }
    try:
        try:
            ROBOT.stop()
        except Exception:
            pass
        if TELEOP["engaged"] or TELEOP["calibration"]:
            TELEOP.update({"engaged": False, "token": None, "source": None, "holding": False})
            set_teleop_calibration({})
            print("[stage2] teleop dropped: session relaunched", flush=True)
        ROBOT = RobotAdapter()
        ROBOT_ERROR = None
        LAST_MOTION = {"linear": 0.0, "lateral": 0.0, "angular": 0.0, "source": "none"}
        LAST_MOTION_AT = 0.0
        WATCHDOG_STOPPED = True

        CURRENT_SCENE = dict(scene)
        CURRENT_ROBOT = dict(robot_cfg)
        CURRENT_SCENE_URL = load_scene(scene)
        set_camera(scene)
        ROBOT = adapter_cls(robot_cfg, scene)
        # Only reframe when the robot is small relative to the scene camera --
        # a wheeled base in a warehouse is meant to be seen in context.
        if robot_cfg.get("adapter") == "joint-position" or robot_cfg.get("frame_on_load"):
            frame_robot(str(robot_cfg["prim_path"]), camera_defaults())
        # After framing, never before: the follow offset is the distance from
        # the robot to wherever the camera ended up, and taking it while the
        # camera was still at the scene's default made the first update yank
        # the view somewhere unrelated.

        SESSION.update({"status": "ready", "launchedAt": time.time(), "error": None})
        print(f"[stage2] session ready scene={scene_id} robot={robot_id}", flush=True)
    except Exception as exc:
        ROBOT_ERROR = f"{type(exc).__name__}: {exc}"
        SESSION.update({"status": "error", "error": ROBOT_ERROR})
        traceback.print_exc()
        print(f"[stage2] launch failed scene={scene_id} robot={robot_id}: {ROBOT_ERROR}", flush=True)
    return session_info()


