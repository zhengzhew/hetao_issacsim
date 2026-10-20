# MicroDuck integration from the supplied microduck-bundle.
# OSRBOT/Pollen attribution and license notices: ../../third_party/MicroDuck-*.
"""Pure control contract for the MicroDuck integration.

This module deliberately has no Isaac Sim or ONNX dependency.  The constants
and runtime defaults are aligned with the public OSRBOT MicroDuck Isaac
playground and the Pollen MicroDuck runtime.  Keeping them here makes the
policy boundary testable without launching Kit.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Sequence

POLICY_JOINTS = (
    "left_hip_yaw",
    "left_hip_roll",
    "left_hip_pitch",
    "left_knee",
    "left_ankle",
    "neck_pitch",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "right_hip_yaw",
    "right_hip_roll",
    "right_hip_pitch",
    "right_knee",
    "right_ankle",
)

HOME_POSE = (
    0.0,
    -0.0873,
    -0.4579,
    -0.0049,
    0.4530,
    0.3491,
    0.3491,
    0.0,
    0.0,
    0.0,
    0.0873,
    0.4579,
    0.0049,
    -0.4530,
)

OBSERVATION_SIZE = 61
ACTION_SIZE = 14
COMMAND_SIZE = 13
PHYSICS_HZ = 200.0
CONTROL_DECIMATION = 4
CONTROL_HZ = PHYSICS_HZ / CONTROL_DECIMATION

# Pinned public runtime/playground defaults.
WALKING_ACTION_SCALE = 0.9
SKILL_ACTION_SCALE = 1.0
VELOCITY_COMMAND_LIMITS = (0.4, 0.3, 1.0)
HEAD_TARGET_ALPHA = 0.5
LEGS_TARGET_ALPHA = 0.7
POLICY_SWITCH_THRESHOLD = 0.05

_HEAD_INDICES = frozenset(range(5, 9))


def _finite(value: object, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def clamp_velocity_command(
    command: Sequence[float],
    limits: Sequence[float] = VELOCITY_COMMAND_LIMITS,
) -> tuple[float, float, float]:
    """Clamp ``[vx, vy, yaw_rate]`` to the public MicroDuck runtime envelope."""
    if len(command) != 3 or len(limits) != 3:
        raise ValueError("velocity command and limits must both contain three values")
    out = []
    for index, (value, limit) in enumerate(zip(command, limits, strict=True)):
        number = _finite(value, f"command[{index}]")
        bound = abs(_finite(limit, f"limit[{index}]"))
        out.append(max(-bound, min(bound, number)))
    return tuple(out)  # type: ignore[return-value]


def moving_command(command: Iterable[float], threshold: float = POLICY_SWITCH_THRESHOLD) -> bool:
    """Return true when the velocity vector is large enough to select walking."""
    values = [_finite(value, "command") for value in command]
    if len(values) != 3:
        raise ValueError("velocity command must contain three values")
    threshold = max(0.0, _finite(threshold, "threshold"))
    return math.sqrt(sum(value * value for value in values)) > threshold


def action_scale_for_policy(filename: str, fallback: float = SKILL_ACTION_SCALE) -> float:
    """Return the known runtime scale for released locomotion policies."""
    name = Path(str(filename)).name.lower()
    if name == "alpha_walking.onnx":
        return WALKING_ACTION_SCALE
    return _finite(fallback, "fallback action scale")


def smooth_position_targets(
    raw: Sequence[float],
    previous: Sequence[float],
    *,
    head_alpha: float = HEAD_TARGET_ALPHA,
    legs_alpha: float = LEGS_TARGET_ALPHA,
) -> tuple[float, ...]:
    """Apply the public playground's target smoothing by policy-joint group.

    ``alpha`` is the fraction of the new target used on this control tick.
    The four neck/head joints use ``head_alpha``; the ten leg joints use
    ``legs_alpha``.
    """
    if len(raw) != ACTION_SIZE or len(previous) != ACTION_SIZE:
        raise ValueError(f"targets must contain {ACTION_SIZE} values")
    head_alpha = _finite(head_alpha, "head_alpha")
    legs_alpha = _finite(legs_alpha, "legs_alpha")
    if not 0.0 <= head_alpha <= 1.0 or not 0.0 <= legs_alpha <= 1.0:
        raise ValueError("target filter alpha must be between 0 and 1")

    out = []
    for index, (current, old) in enumerate(zip(raw, previous, strict=True)):
        current = _finite(current, f"raw[{index}]")
        old = _finite(old, f"previous[{index}]")
        alpha = head_alpha if index in _HEAD_INDICES else legs_alpha
        out.append(alpha * current + (1.0 - alpha) * old)
    return tuple(out)


def validate_contract() -> None:
    if len(POLICY_JOINTS) != ACTION_SIZE:
        raise AssertionError("policy joint order must contain 14 joints")
    if len(HOME_POSE) != ACTION_SIZE:
        raise AssertionError("home pose must contain 14 values")
    proprioception = 3 + 3 + ACTION_SIZE + ACTION_SIZE + ACTION_SIZE
    if proprioception + COMMAND_SIZE != OBSERVATION_SIZE:
        raise AssertionError("MicroDuck observation contract must remain 61-dimensional")


validate_contract()
