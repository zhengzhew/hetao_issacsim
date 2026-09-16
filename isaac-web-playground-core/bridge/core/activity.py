"""Idle-throttling: slow the main loop when nobody is watching or moving.

Nothing here changes what the simulation does; it changes how often it is
asked to do it when nobody is looking. The conditions are deliberately
conservative: a robot mid-experiment that someone simply is not watching must
not be slowed down, so a recent motion command counts as activity too.
"""
from __future__ import annotations

import time

from .app_context import ARGS
from .teleop import TELEOP

START_TIME = time.monotonic()
ACTIVITY = {"last_capture": 0.0, "last_command": 0.0, "idle_since": 0.0, "was_idle": False}


ACTIVITY = {"last_capture": 0.0, "last_command": 0.0, "idle_since": 0.0, "was_idle": False}


def note_activity(kind: str) -> None:
    ACTIVITY["last_capture" if kind == "capture" else "last_command"] = time.monotonic()


def idle_seconds() -> float:
    if TELEOP["engaged"]:
        return 0.0
    newest = max(ACTIVITY["last_capture"], ACTIVITY["last_command"])
    if newest <= 0.0:
        newest = START_TIME
    return time.monotonic() - newest


def throttle_when_idle() -> None:
    """Sleep between updates while nothing is watching or moving."""
    if ARGS.idle_after <= 0 or ARGS.idle_hz <= 0:
        return
    quiet = idle_seconds()
    if quiet < ARGS.idle_after:
        if ACTIVITY["was_idle"]:
            ACTIVITY["was_idle"] = False
            print(f"[stage2] active again after {quiet:.0f}s idle", flush=True)
        return
    if not ACTIVITY["was_idle"]:
        ACTIVITY["was_idle"] = True
        print(f"[stage2] idle: no viewer, teleop or command for {ARGS.idle_after:g}s; "
              f"slowing the loop to {ARGS.idle_hz:g} Hz", flush=True)
    # A plain sleep: the loop still runs, just far less often.
    time.sleep(max(0.0, 1.0 / ARGS.idle_hz))

