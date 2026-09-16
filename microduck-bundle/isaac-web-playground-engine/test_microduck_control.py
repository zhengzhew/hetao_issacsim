from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))

from microduck.control import (  # noqa: E402
    HOME_POSE,
    action_scale_for_policy,
    clamp_velocity_command,
    moving_command,
    smooth_position_targets,
)


class MicroDuckControlTests(unittest.TestCase):
    def test_runtime_command_limits(self) -> None:
        self.assertEqual(clamp_velocity_command((0.8, -0.8, 2.0)), (0.4, -0.3, 1.0))

    def test_walking_uses_pinned_scale(self) -> None:
        self.assertAlmostEqual(action_scale_for_policy("alpha_walking.onnx"), 0.9)
        self.assertAlmostEqual(action_scale_for_policy("alpha_stand.onnx"), 1.0)

    def test_switch_threshold_ignores_tiny_noise(self) -> None:
        self.assertFalse(moving_command((0.01, 0.0, 0.0)))
        self.assertTrue(moving_command((0.06, 0.0, 0.0)))

    def test_target_filter_is_group_specific(self) -> None:
        previous = tuple(HOME_POSE)
        raw = tuple(value + 1.0 for value in HOME_POSE)
        filtered = smooth_position_targets(raw, previous, head_alpha=0.5, legs_alpha=0.7)
        self.assertAlmostEqual(filtered[0] - previous[0], 0.7)
        self.assertAlmostEqual(filtered[5] - previous[5], 0.5)
        self.assertAlmostEqual(filtered[9] - previous[9], 0.7)


if __name__ == "__main__":
    unittest.main()
