"""Leader/follower teleoperation: calibration, sampling, watchdog."""
from __future__ import annotations

from .app_context import ARGS, deque, math, time, uuid
from . import session
from .uploads import _json_safe

# --- leader / follower teleoperation ---------------------------------------
#
# The leader arm is physical hardware on a serial port, so it cannot live in
# this process. A small client reads it wherever it is plugged in and streams
# joint samples here; this side maps them onto the follower in the simulation.
# Keeping the mapping on this side means the client stays dumb and the same
# client works for any follower.

TELEOP = {
    "engaged": False,
    "token": None,
    "source": None,
    "seq": 0,
    "dropped": 0,
    "applied": 0,
    "last_sample_at": 0.0,
    "last_positions": {},
    "raw": {},
    "rate_hz": 0.0,
    "holding": False,
    "error": None,
    # Per joint: follower = clamp(scale * (raw - offset)), optionally inverted.
    "calibration": {},
}
_TELEOP_TIMES: "deque[float]" = deque(maxlen=60)


def teleop_calibration() -> dict:
    return dict(TELEOP["calibration"])


def set_teleop_calibration(mapping: dict) -> dict:
    """mapping: {follower_joint: {source, offset, scale, invert}}"""
    cleaned: dict[str, dict] = {}
    for name, spec in (mapping or {}).items():
        if not isinstance(spec, dict):
            raise ValueError(f"calibration for {name} must be an object")
        entry = {
            "source": str(spec.get("source") or name),
            "offset": float(spec.get("offset", 0.0)),
            "scale": float(spec.get("scale", 1.0)),
            "invert": bool(spec.get("invert", False)),
        }
        if not all(math.isfinite(entry[k]) for k in ("offset", "scale")):
            raise ValueError(f"calibration for {name} must use finite numbers")
        if entry["scale"] == 0.0:
            raise ValueError(f"calibration scale for {name} cannot be zero")
        cleaned[str(name)] = entry
    TELEOP["calibration"] = cleaned
    return cleaned


def _map_sample(raw: dict) -> dict:
    """Turn one leader sample into follower joint targets."""
    calibration = TELEOP["calibration"]
    names = getattr(session.ROBOT, "dof_names", []) or []
    out: dict[str, float] = {}
    if calibration:
        for follower_joint, spec in calibration.items():
            if follower_joint not in names:
                continue
            value = raw.get(spec["source"])
            if value is None:
                continue
            mapped = spec["scale"] * (float(value) - spec["offset"])
            if spec["invert"]:
                mapped = -mapped
            out[follower_joint] = mapped
        return out
    # No calibration: pass through any joint whose name the follower knows.
    for name, value in raw.items():
        if name in names:
            out[name] = float(value)
    return out


def teleop_engage(args: dict) -> dict:
    if not getattr(session.ROBOT, "set_joints", None):
        raise ValueError("the active robot is not joint driven; teleop needs an arm")
    if not getattr(session.ROBOT, "limits", None) and not (args or {}).get("allow_unlimited"):
        raise ValueError(
            "joint limits could not be read for this robot, so a leader could drive it "
            "into its hard stops; pass allow_unlimited to override")
    if TELEOP["engaged"]:
        if args.get("requestId") and args["requestId"] == TELEOP.get("request_id") and args.get("source") == TELEOP["source"]:
            return {**teleop_status(), "token": TELEOP["token"]}
        raise ValueError("another leader is engaged; release control before connecting")
    # A calibration belongs to the session that supplied it. Carrying one over
    # would silently apply another operator's offsets and inversions -- and
    # would survive a robot swap it no longer describes.
    set_teleop_calibration(args.get("calibration") or {})
    if TELEOP["engaged"]:
        print(f"[stage2] teleop taken over from {TELEOP['source']}", flush=True)
    TELEOP.update({
        "engaged": True,
        # Samples must carry this. It is what stops a killed leader's in-flight
        # samples from driving the arm, or wedging the next leader's sequence.
        "token": uuid.uuid4().hex[:16],
        "source": str(args.get("source") or "unknown"),
        "request_id": args.get("requestId"),
        "seq": 0,
        "dropped": 0,
        "applied": 0,
        "error": None,
        "holding": False,
        "last_sample_at": time.monotonic(),
        # The follower is wherever it is; the first samples ramp toward the
        # leader at max_step rather than jumping.
        "last_positions": {k: v for k, v in (getattr(session.ROBOT, "targets", {}) or {}).items()
                           if isinstance(v, (int, float)) and math.isfinite(v)},
    })
    _TELEOP_TIMES.clear()
    print(f"[stage2] teleop engaged source={TELEOP['source']} "
          f"calibrated={bool(TELEOP['calibration'])} max_step={ARGS.teleop_max_step}", flush=True)
    # Only the reply to engage carries the token; teleop_status() is public.
    return {**teleop_status(), "token": TELEOP["token"]}


def teleop_disengage(args: dict | None = None) -> dict:
    token = (args or {}).get("token")
    if TELEOP["engaged"] and token and token != TELEOP["token"]:
        # A leader that has already been replaced must not stop the new one.
        return {**teleop_status(), "ignored": "that leader is no longer engaged"}
    if TELEOP["engaged"]:
        print(f"[stage2] teleop disengaged ({TELEOP['source']})", flush=True)
    TELEOP.update({"engaged": False, "token": None, "source": None, "holding": False})
    set_teleop_calibration({})
    try:
        session.ROBOT.stop()
    except Exception:
        pass
    return teleop_status()


def teleop_sample(args: dict) -> dict:
    """One leader sample. Called at the leader's rate, so it stays cheap."""
    started = time.perf_counter()
    if not TELEOP["engaged"]:
        TELEOP["dropped"] += 1
        return {"applied": False, "reason": "teleop is not engaged"}
    raw = args.get("positions") or args.get("joints") or {}
    if not isinstance(raw, dict) or not raw:
        raise ValueError("a teleop sample needs a positions object")
    if len(raw) > 64:
        raise ValueError("too many joints in one sample")
    clean_raw = {}
    for name, value in raw.items():
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"joint {name} is not a finite number")
        clean_raw[str(name)] = number

    token = args.get("token")
    if TELEOP["token"] and token != TELEOP["token"]:
        TELEOP["dropped"] += 1
        return {"applied": False, "reason": "another leader is engaged", "reengage": True}

    seq = int(args.get("seq") or 0)
    # Samples can overtake each other on a lossy link; an old one is worthless.
    if seq and seq <= TELEOP["seq"]:
        TELEOP["dropped"] += 1
        return {"applied": False, "reason": "stale sample", "seq": TELEOP["seq"]}

    targets = _map_sample(clean_raw)
    if not targets:
        TELEOP["dropped"] += 1
        return {"applied": False, "reason": "no leader joint matched a follower joint"}

    # Slew limit. Without it the very first sample is an unbounded step from
    # wherever the follower is to wherever the leader happens to be.
    # Preserve the old 20 Hz nominal speed, independent of actual packet rate.
    elapsed = max(0., min(time.monotonic() - TELEOP["last_sample_at"], .1))
    step = float(ARGS.teleop_max_step) * 20.0 * elapsed
    previous = TELEOP["last_positions"] or {}
    limited = {}
    clamped_any = False
    for name, wanted in targets.items():
        current = previous.get(name)
        if current is None or float(ARGS.teleop_max_step) <= 0:
            limited[name] = wanted
            continue
        delta = wanted - current
        if abs(delta) > step:
            limited[name] = current + math.copysign(step, delta)
            clamped_any = True
        else:
            limited[name] = wanted
    targets = limited

    result = session.ROBOT.set_joints(targets, False)
    # Track what was actually applied, not what was asked for.
    applied_targets = (result or {}).get("targets")
    if isinstance(applied_targets, dict) and applied_targets:
        targets = {name: float(value) for name, value in applied_targets.items()}
    now = time.monotonic()
    _TELEOP_TIMES.append(now)
    if len(_TELEOP_TIMES) > 1:
        span = _TELEOP_TIMES[-1] - _TELEOP_TIMES[0]
        TELEOP["rate_hz"] = round((len(_TELEOP_TIMES) - 1) / span, 1) if span > 0 else 0.0
    TELEOP.update({
        "seq": seq or TELEOP["seq"] + 1,
        "applied": TELEOP["applied"] + 1,
        "last_sample_at": now,
        "last_positions": targets,
        "raw": clean_raw,
        "holding": False,
    })
    return {"applied": True, "targets": targets, "seq": TELEOP["seq"],
            "rate_hz": TELEOP["rate_hz"], "slew_limited": clamped_any,
            # Time spent inside the bridge. Subtract it from what the client
            # measures and the remainder is queueing plus network.
            "bridge_ms": round((time.perf_counter() - started) * 1000, 2),
            "result": result}


def teleop_status() -> dict:
    idle = time.monotonic() - TELEOP["last_sample_at"] if TELEOP["last_sample_at"] else None
    return _json_safe({
        "engaged": TELEOP["engaged"],
        "has_token": bool(TELEOP["token"]),
        "source": TELEOP["source"],
        "max_step": ARGS.teleop_max_step,
        "seq": TELEOP["seq"],
        "applied": TELEOP["applied"],
        "dropped": TELEOP["dropped"],
        "rate_hz": TELEOP["rate_hz"],
        "holding": TELEOP["holding"],
        "idle_seconds": round(idle, 3) if idle is not None else None,
        "hold_after_seconds": ARGS.teleop_watchdog,
        "calibration": TELEOP["calibration"],
        "last_positions": TELEOP["last_positions"],
        "raw": TELEOP["raw"],
        "error": TELEOP["error"],
        "follower_joints": list(getattr(session.ROBOT, "dof_names", []) or []),
    })


def enforce_teleop_watchdog() -> None:
    """If the leader stops sending, hold the last pose. Never drop the arm."""
    if TELEOP["engaged"] and TELEOP["last_sample_at"] and time.monotonic() - TELEOP["last_sample_at"] > 5.0:
        teleop_disengage({"token": TELEOP["token"]})
        return
    if not TELEOP["engaged"] or TELEOP["holding"] or not TELEOP["last_sample_at"]:
        return
    if time.monotonic() - TELEOP["last_sample_at"] <= ARGS.teleop_watchdog:
        return
    TELEOP["holding"] = True
    try:
        session.ROBOT.stop()   # for an arm this holds position rather than zeroing it
    except Exception:
        pass
    print("[stage2] teleop leader went quiet; holding position", flush=True)

