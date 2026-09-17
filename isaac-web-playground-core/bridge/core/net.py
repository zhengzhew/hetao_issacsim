"""Wire protocol: op dispatch, request queue, idle watchdog, TCP server."""
from __future__ import annotations

from .app_context import (ARGS, CONFIG, json, kit, math, omni, queue, socket,
                          socketserver, sys, threading, time, traceback)
from . import catalog, session
from .catalog import reload_catalog
from .uploads import inspect_asset
from .streaming import CAMERA, _CAPTURE, _capture_available, apply_camera, camera_defaults, capture_frame, finish_capture, frame_robot
from .teleop import TELEOP, set_teleop_calibration, teleop_disengage, teleop_engage, teleop_sample, teleop_status, enforce_teleop_watchdog
from .session import launch_session, robot_info, session_info
from .activity import ACTIVITY, idle_seconds, note_activity, throttle_when_idle

def stage_info() -> dict:
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        return {"scene": session.CURRENT_SCENE, "sceneUrl": session.CURRENT_SCENE_URL, "prim_count": 0, "prims": []}
    prims = []
    total = 0
    for prim in stage.Traverse():
        total += 1
        p = str(prim.GetPath())
        if p.count("/") <= 2 and len(prims) < 200:
            prims.append({"path": p, "type": prim.GetTypeName()})
    return {"scene": session.CURRENT_SCENE, "sceneUrl": session.CURRENT_SCENE_URL, "prim_count": total, "prims": prims}


def dispatch(op: str, args: dict) -> object:
    timeline = omni.timeline.get_timeline_interface()
    if op == "policy_status":
        # This build has no MicroDuck policy engine. Report that explicitly
        # instead of emitting an exception for every frontend status poll.
        return {"available": False, "engaged": False}
    if op == "ping":
        return {
            "service": "isaac-web-playground-stage2",
            "playing": bool(timeline.is_playing()),
            "mock": False,
            "session": session_info(),
            "robot": robot_info(),
            "watchdog_seconds": ARGS.watchdog,
            "stream": {
                "public_ip": ARGS.public_ip,
                "signal_port": ARGS.signal_port,
                "media_port": ARGS.stream_port,
                "livestream": bool(ARGS.livestream),
            },
            "render": {
                "width": CONFIG["width"], "height": CONFIG["height"], "hide_ui": CONFIG["hide_ui"],
                "multi_gpu": CONFIG.get("multi_gpu"), "gpu": CONFIG.get("active_gpu"),
            },
            "idle": {
                "seconds": round(idle_seconds(), 1),
                "throttled": ACTIVITY["was_idle"],
                "after_seconds": ARGS.idle_after,
                "hz": ARGS.idle_hz,
            },
            "capture": {
                "available": _capture_available(),
                "width": ARGS.capture_width,
                "height": ARGS.capture_height,
                "encoder": _CAPTURE["encoder"],
                "error": _CAPTURE["error"],
            },
        }
    if op == "get_catalog":
        return {"scenes": catalog.SCENES, "robots": catalog.ROBOTS}
    if op == "reload_catalog":
        return reload_catalog()
    if op == "get_session":
        return session_info()
    if op == "launch_session":
        return launch_session(str(args.get("sceneId") or ""), str(args.get("robotId") or ""))
    if op == "teleop_engage":
        return teleop_engage(args or {})
    if op == "teleop_disengage":
        return teleop_disengage(args or {})
    if op == "teleop_sample":
        return teleop_sample(args or {})
    if op == "teleop_status":
        return teleop_status()
    if op == "teleop_calibrate":
        payload = args or {}
        if TELEOP["engaged"] and TELEOP["token"] and payload.get("token") != TELEOP["token"]:
            raise ValueError("only the engaged leader may change the calibration")
        mapping = set_teleop_calibration(payload.get("calibration") or {})
        # A remap changes what every joint means; re-seed the integrator from
        # where the arm actually is so it ramps rather than jumps.
        TELEOP["last_positions"] = dict(getattr(session.ROBOT, "targets", {}) or {})
        return {"calibration": mapping}
    if op == "set_drive_gains":
        setter = getattr(session.ROBOT, "apply_drive_gains", None)
        if setter is None:
            raise ValueError("the active robot has no joint drives")
        overrides = (args or {}).get("gains") or {}
        if not isinstance(overrides, dict):
            raise ValueError("gains must be an object")
        for name, spec in overrides.items():
            if not isinstance(spec, dict):
                raise ValueError(f"gains for {name} must be an object")
            for key, value in spec.items():
                if key not in ("stiffness", "damping", "max_force"):
                    raise ValueError(f"unknown gain {key}")
                number = float(value)
                if not math.isfinite(number) or not (0.0 <= number <= 1e6):
                    raise ValueError(f"{key} for {name} is out of range")
        return {"gains": setter(overrides)}
    if op == "set_joints":
        positions = args.get("positions") or args.get("joints") or {}
        if not isinstance(positions, dict) or not positions:
            raise ValueError("set_joints needs a positions object")
        if len(positions) > 64:
            raise ValueError("too many joints in one command")
        if TELEOP["engaged"] and not args.get("force"):
            raise ValueError(f"a leader arm is driving this robot ({TELEOP['source']}); disengage it first")
        note_activity("command")
        setter = getattr(session.ROBOT, "set_joints", None)
        if setter is None:
            raise ValueError("the active robot is not joint driven")
        return setter(positions, bool(args.get("relative")))
    if op == "get_joints":
        return {"info": robot_info(), "pose": session.ROBOT.pose()}
    if op == "inspect_asset":
        return inspect_asset(args or {})
    if op == "capture_frame":
        return capture_frame(args or {})
    if op == "get_camera":
        return {"camera": dict(CAMERA), "defaults": camera_defaults()}
    if op == "set_camera":
        return apply_camera(list(args.get("eye") or CAMERA["eye"]), list(args.get("target") or CAMERA["target"]))
    if op == "reset_camera":
        defaults = camera_defaults()
        if not (args or {}).get("scene_view") and session.CURRENT_ROBOT:
            framed = frame_robot(str(session.CURRENT_ROBOT["prim_path"]), defaults)
            if framed:
                return framed
        return apply_camera(defaults["eye"], defaults["target"])
    if op == "frame_robot":
        if not session.CURRENT_ROBOT:
            raise ValueError("no robot is loaded")
        margin = float((args or {}).get("margin", 1.15))
        if not math.isfinite(margin) or not 0.6 <= margin <= 6.0:
            raise ValueError("margin must be between 0.6 (very tight) and 6.0 (far back)")
        framed = frame_robot(str(session.CURRENT_ROBOT["prim_path"]), camera_defaults(), margin)
        if not framed:
            raise ValueError("could not measure the robot; its bounding box came back empty")
        return framed
    if op == "get_scene_info":
        return stage_info()
    if op == "get_robot_info":
        return robot_info()
    if op == "get_robot_pose":
        return {"pose": session.ROBOT.pose()}
    if op == "reset_robot":
        if TELEOP["engaged"] and not (args or {}).get("force"):
            raise ValueError(f"a leader arm is driving this robot ({TELEOP['source']}); disengage it first")
        result = session.ROBOT.reset()
        # Keep the slew integrator with the arm, or the next sample jumps.
        TELEOP["last_positions"] = dict(getattr(session.ROBOT, "targets", {}) or {})
        return result
    if op in {"motion", "teleop"}:
        linear = float(args.get("linear", 0.0))
        lateral = float(args.get("lateral", 0.0))
        angular = float(args.get("angular", 0.0))
        if abs(linear) > 2.0 or abs(lateral) > 2.0 or abs(angular) > 4.0:
            raise ValueError("motion command exceeds playground safety bounds")
        note_activity("command")
        session.LAST_MOTION = {"linear": linear, "lateral": lateral, "angular": angular, "source": str(args.get("source", "web-keyboard"))}
        session.LAST_MOTION_AT = time.monotonic()
        session.WATCHDOG_STOPPED = linear == 0.0 and lateral == 0.0 and angular == 0.0
        return session.ROBOT.apply_motion(linear, lateral, angular)
    raise ValueError(f"unknown op: {op}")


LOOP_TIMING = {"n": 0, "requests": 0.0, "policy": 0.0, "render": 0.0, "at": 0.0}


def note_loop_timing(requests: float, policy: float, render: float) -> None:
    """Where the loop's time goes, once a minute.

    Three guesses at what made the loop slow -- the physics stepping, the
    capture resolution, the configured frame cap -- were all wrong, and each
    cost a restart to disprove. Timing the phases answered it in one run:
    rendering was 70 ms of an 80 ms iteration because the bridge had been
    launched with --no-multi-gpu.

    Left in at a minute's interval rather than removed. It is one line, and
    the next person to ask why the stream is slow gets the answer from the
    log instead of from a series of experiments.
    """
    LOOP_TIMING["n"] += 1
    LOOP_TIMING["requests"] += requests
    LOOP_TIMING["policy"] += policy
    LOOP_TIMING["render"] += render
    now = time.monotonic()
    if LOOP_TIMING["at"] <= 0.0:
        LOOP_TIMING["at"] = now
        return
    if now - LOOP_TIMING["at"] < 60.0:
        return
    n = max(LOOP_TIMING["n"], 1)
    span = now - LOOP_TIMING["at"]
    print(f"[stage2] loop {n / span:5.1f} Hz over {span:.0f}s | per iteration: "
          f"requests+capture {LOOP_TIMING['requests'] / n * 1000:6.1f} ms, "
          f"policy {LOOP_TIMING['policy'] / n * 1000:6.1f} ms, "
          f"render {LOOP_TIMING['render'] / n * 1000:6.1f} ms", flush=True)
    LOOP_TIMING.update({"n": 0, "requests": 0.0, "policy": 0.0, "render": 0.0, "at": now})


WORK: "queue.Queue[tuple[str, dict, queue.Queue]]" = queue.Queue(maxsize=256)


# Frames are worthless once they are late; scene loads legitimately take minutes.
OP_TIMEOUTS = {"capture_frame": 20.0, "launch_session": 300.0, "inspect_asset": 90.0}


def submit(op: str, args: dict, timeout: float | None = None):
    if op == "capture_frame":
        args = dict(args or {}, _defer_encode=True)
    if timeout is None:
        timeout = OP_TIMEOUTS.get(op, 60.0)
    reply: "queue.Queue[tuple[bool, object]]" = queue.Queue(maxsize=1)
    try:
        WORK.put((op, args, reply), timeout=5.0)
    except queue.Full:
        raise RuntimeError("bridge is saturated; try again")
    try:
        ok, payload = reply.get(timeout=timeout)
    except queue.Empty:
        raise RuntimeError(f"{op} did not finish within {timeout:g}s") from None
    if ok:
        return finish_capture(payload) if op == "capture_frame" else payload
    raise RuntimeError(payload)


def drain() -> None:
    pending: list[tuple[str, dict, "queue.Queue"]] = []
    while True:
        try:
            pending.append(WORK.get_nowait())
        except queue.Empty:
            break

    # Only the newest frame request is worth rendering; the rest are already
    # stale by the time we get here, and each would cost its own kit.update().
    last_capture = max((i for i, item in enumerate(pending) if item[0] == "capture_frame"), default=-1)

    # Run the arm before the camera. A teleop sample is a control input with a
    # human waiting on it; a frame is a picture that can be 30 ms later.
    order = sorted(range(len(pending)), key=lambda i: 0 if pending[i][0] == "teleop_sample" else 1)

    for index in order:
        op, args, reply = pending[index]
        if op == "capture_frame" and index != last_capture:
            reply.put((False, "superseded by a newer frame request"))
            continue
        try:
            reply.put((True, dispatch(op, args or {})))
        except Exception as exc:
            traceback.print_exc()
            reply.put((False, f"{type(exc).__name__}: {exc}"))
        # A long op must not be able to suspend either watchdog.
        enforce_watchdog()
        enforce_teleop_watchdog()


# --- idle throttling --------------------------------------------------------
#
# Nothing here changes what the simulation does; it changes how often it is
# asked to do it when nobody is looking. The conditions are deliberately
# conservative: a robot mid-experiment that someone simply is not watching must
# not be slowed down, so a recent motion command counts as activity too.



def enforce_watchdog() -> None:
    if session.WATCHDOG_STOPPED or session.LAST_MOTION_AT <= 0:
        return
    if time.monotonic() - session.LAST_MOTION_AT > ARGS.watchdog:
        session.ROBOT.stop()
        session.WATCHDOG_STOPPED = True
        print("[stage2] motion watchdog stop", flush=True)


MAX_LINE_BYTES = 256 * 1024


class Handler(socketserver.StreamRequestHandler):
    timeout = 300.0

    def handle(self) -> None:
        try:
            while True:
                raw = self.rfile.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    return
                if len(raw) > MAX_LINE_BYTES:
                    self._reply({"id": None, "ok": False, "error": "command line too long"})
                    return
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                msg_id = None
                try:
                    msg = json.loads(line)
                    msg_id = msg.get("id")
                    result = submit(str(msg["op"]), msg.get("args") or {})
                    payload = {"id": msg_id, "ok": True, "result": result}
                except Exception as exc:
                    payload = {"id": msg_id, "ok": False, "error": str(exc)}
                self._reply(payload)
        except (OSError, ConnectionError):
            # The client went away mid-request. Routine; not worth a traceback.
            return

    def _reply(self, payload: dict) -> None:
        self.wfile.write((json.dumps(payload) + "\n").encode("utf-8"))
        self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    # On Windows SO_REUSEADDR permits hijacking a live listening socket, so a
    # restart could bind alongside a hung instance and split traffic between
    # them. Better to fail fast and let the supervisor retry.
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True
    address_family = socket.AF_INET
