"""Stage loading and scene-level camera placement."""
from __future__ import annotations

from .app_context import is_stage_loading, kit, omni, open_stage, time
from .streaming import CAMERA, _release_capture
from .catalog import asset_url

def wait_for_stage(timeout_seconds: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        kit.update()
        if not is_stage_loading():
            for _ in range(6):
                kit.update()
            return
    raise TimeoutError("USD stage load timed out")


def load_scene(scene: dict) -> str:
    timeline = omni.timeline.get_timeline_interface()
    try:
        timeline.stop()
    except Exception:
        pass
    for _ in range(3):
        kit.update()
    _release_capture()
    url = asset_url(scene["asset_path"])
    print(f"[stage2] opening scene id={scene['id']} url={url}", flush=True)
    result = open_stage(url)
    if result is False:
        raise RuntimeError(f"open_stage returned False: {url}")
    wait_for_stage()
    return url


def set_camera(scene: dict) -> None:
    eye = list(scene.get("camera_eye") or [4.0, -5.0, 3.0])
    target = list(scene.get("camera_target") or [0.0, 0.0, 0.4])
    CAMERA["eye"] = [float(v) for v in eye]
    CAMERA["target"] = [float(v) for v in target]
    try:
        from isaacsim.core.utils.viewports import set_camera_view
        set_camera_view(eye=eye, target=target, camera_prim_path="/OmniverseKit_Persp")
        return
    except Exception:
        pass
    try:
        from isaacsim.core.experimental.utils.viewports import set_camera_view
        set_camera_view(eye=eye, target=target, camera_prim_path="/OmniverseKit_Persp")
    except Exception as exc:
        print(f"[stage2] camera setup skipped: {exc}", flush=True)


def robot_spawn(scene: dict, robot: dict) -> list[float]:
    """Where to put this robot in this scene.

    A scene's spawn point is authored for a mobile base -- somewhere with room
    to drive. A table-top arm wants none of that: the reference SO-101 setup
    puts the arm at the origin and builds a 30 cm workspace around it. Dropping
    it at a warehouse's driving spawn gives a tiny arm alone on a big floor,
    which is what "I cannot find the robot" actually looks like.
    """
    if robot.get("spawn_at_origin", robot.get("adapter") == "joint-position"):
        xyz = list(robot.get("spawn") or [0.0, 0.0, 0.0])
    else:
        xyz = list(scene.get("spawn") or [0.0, 0.0, 0.0])
    while len(xyz) < 3:
        xyz.append(0.0)
    xyz[2] = float(robot.get("spawn_z", xyz[2]))
    return [float(x) for x in xyz[:3]]


