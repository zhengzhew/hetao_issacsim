#!/usr/bin/env python3
"""Validate the host-independent MicroDuck runtime contract in a robot catalog."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))

from microduck.control import (  # noqa: E402
    ACTION_SIZE,
    COMMAND_SIZE,
    OBSERVATION_SIZE,
    POLICY_JOINTS,
    VELOCITY_COMMAND_LIMITS,
    action_scale_for_policy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=ROOT / "configs/uploads/microduck.example.json",
    )
    args = parser.parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    robots = payload.get("robots") or []
    if len(robots) != 1:
        raise ValueError("expected exactly one robot in the MicroDuck example catalog")
    robot = robots[0]
    policy = robot.get("policy") or {}

    checks: list[tuple[str, bool, str]] = []
    joints = tuple(policy.get("joints") or ())
    checks.append(("policy joint order", joints == POLICY_JOINTS, f"{len(joints)} joints"))
    checks.append(("observation size", policy.get("obs_size") == OBSERVATION_SIZE, str(policy.get("obs_size"))))
    checks.append(("command size", policy.get("command_size") == COMMAND_SIZE, str(policy.get("command_size"))))
    checks.append(("action size/home", len(policy.get("home") or ()) == ACTION_SIZE, str(len(policy.get("home") or ()))))
    checks.append(("physics rate", float(policy.get("physics_hz", 0)) == 200.0, str(policy.get("physics_hz"))))
    checks.append(("decimation", int(policy.get("decimation", 0)) == 4, str(policy.get("decimation"))))
    limits = tuple(float(v) for v in (policy.get("command_limits") or ()))
    checks.append(("command limits", limits == VELOCITY_COMMAND_LIMITS, str(limits)))
    walk_scale = float((policy.get("action_scale_by_file") or {}).get("alpha_walking.onnx", math.nan))
    checks.append(("walking action scale", walk_scale == action_scale_for_policy("alpha_walking.onnx"), str(walk_scale)))
    filt = policy.get("target_filter") or {}
    checks.append(("target filter", filt.get("head_alpha") == 0.5 and filt.get("legs_alpha") == 0.7, str(filt)))

    failed = False
    for label, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL':4}  {label:<24} {detail}")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
