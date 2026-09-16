"""One hook for optional add-ons, e.g. the MicroDuck policy engine.

adapters.JointPositionAdapter.info() calls duck_policy_driven() to report
whether a policy is currently driving the robot. Always False here. A
MicroDuck build replaces this function (or this whole module) to report the
real state -- see the separate microduck bundle.
"""
from __future__ import annotations


def duck_policy_driven() -> bool:
    return False
