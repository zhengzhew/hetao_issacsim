#!/usr/bin/env python3
"""Isaac Web Playground - Stage 2 bridge.

Stage 2 responsibilities:
- keep one active Isaac Sim process / WebRTC stream;
- expose a Scene Library and Robot Library from JSON catalogs;
- switch the active scene + robot at runtime through launch_session;
- expose one universal motion API: linear, lateral, angular;
- map that API through adapter families (differential / holonomic);
- preserve watchdog, reset, pose and diagnostics from Stage 1.

Multi-user / multi-GPU / multiple concurrent Isaac processes are intentionally Stage 4.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import queue
import socket
import socketserver
import threading
import time
import sys
import traceback
import uuid
from collections import deque
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--catalog-dir", default=os.environ.get("ISAAC_CATALOG_DIR", ""))
parser.add_argument("--scene-id", default=os.environ.get("ISAAC_DEFAULT_SCENE", "warehouse"))
parser.add_argument("--robot-id", default=os.environ.get("ISAAC_DEFAULT_ROBOT", "jetbot"))
parser.add_argument("--asset-root", default=os.environ.get("ISAAC_ASSET_ROOT", ""))
parser.add_argument("--public-ip", default=os.environ.get("ISAAC_PUBLIC_IP", "127.0.0.1"))
parser.add_argument("--signal-port", type=int, default=int(os.environ.get("ISAAC_SIGNAL_PORT", "49100")))
parser.add_argument("--stream-port", type=int, default=int(os.environ.get("ISAAC_MEDIA_PORT", os.environ.get("ISAAC_STREAM_PORT", "47998"))))
parser.add_argument("--watchdog", type=float, default=float(os.environ.get("ISAAC_MOTION_WATCHDOG", os.environ.get("ISAAC_TELEOP_WATCHDOG", "0.40"))))
parser.add_argument("--capture-width", type=int, default=int(os.environ.get("ISAAC_CAPTURE_WIDTH", "1280")))
parser.add_argument("--capture-height", type=int, default=int(os.environ.get("ISAAC_CAPTURE_HEIGHT", "720")))
# The web server writes uploads here through its own view of the same directory
# (it runs in WSL, this runs on Windows), so the two paths differ by design.
parser.add_argument("--upload-dir", default=os.environ.get("ISAAC_UPLOAD_DIR", ""))
parser.add_argument("--teleop-watchdog", type=float, default=float(os.environ.get("ISAAC_TELEOP_HOLD", "0.50")))
# No joint may move further than this in one sample. This is what stops the
# first sample after engage from being an unbounded jump to an arbitrary pose.
parser.add_argument("--teleop-max-step", type=float, default=float(os.environ.get("ISAAC_TELEOP_MAX_STEP", "0.08")))
# WebRTC costs an NVENC session and a set of streaming threads whether or not
# anything is watching, and it cannot traverse a NATing VPN. The compatibility
# stream is the default path, so livestream is now opt-in.
parser.add_argument("--livestream", dest="livestream", action="store_true",
                    default=os.environ.get("ISAAC_LIVESTREAM", "0").strip().lower() in ("1", "true", "yes", "on"),
                    help="enable the WebRTC livestream (needs a client on the same network)")
parser.add_argument("--no-livestream", dest="livestream", action="store_false")
parser.add_argument("--show-ui", dest="hide_ui", action="store_false", default=None,
                    help="render the Kit editor UI (only visible over WebRTC)")
parser.add_argument("--hide-ui", dest="hide_ui", action="store_true")
parser.add_argument("--render-width", type=int, default=int(os.environ.get("ISAAC_RENDER_WIDTH", "0")))
parser.add_argument("--render-height", type=int, default=int(os.environ.get("ISAAC_RENDER_HEIGHT", "0")))
# This box has two RTX PRO 5000s and a T400, and the log says peer access is
# unavailable -- so every cross-GPU copy goes through main memory. Multi-GPU
# is very likely costing more than it earns here, but that is a claim to
# measure, not to assume, so it is a flag with both directions available.
parser.add_argument("--multi-gpu", dest="multi_gpu", action="store_true", default=None)
parser.add_argument("--no-multi-gpu", dest="multi_gpu", action="store_false")
parser.add_argument("--gpu", type=int, default=int(os.environ.get("ISAAC_GPU", "-1")),
                    help="pin rendering and physics to one device, so training on the box is not disturbed")
# Measured on this box: an idle Isaac Sim burns 33% of one GPU and 26% of
# another with nobody watching, while an extra viewer costs almost nothing.
# The idle cost is the whole game, and it is entirely avoidable.
parser.add_argument("--idle-after", type=float, default=float(os.environ.get("ISAAC_IDLE_AFTER", "5.0")),
                    help="seconds of no viewer, teleop or motion before slowing the loop (0 disables)")
parser.add_argument("--idle-hz", type=float, default=float(os.environ.get("ISAAC_IDLE_HZ", "5.0")),
                    help="loop rate while idle")
ARGS, _UNKNOWN = parser.parse_known_args()

from isaacsim import SimulationApp

# Render no larger than what actually leaves the machine. The compatibility
# stream captures at --capture-width/height, so anything bigger is rendered and
# thrown away; WebRTC wants its own resolution and gets 1280x720.
def _quantise(value: int) -> int:
    """capture_frame rounds down to a multiple of 16; match it exactly."""
    return 1080 if int(value) == 1080 else max(160, (int(value) // 16) * 16)


_render_w = _quantise(ARGS.render_width or (ARGS.capture_width if not ARGS.livestream else 1280))
_render_h = _quantise(ARGS.render_height or (ARGS.capture_height if not ARGS.livestream else 720))
# The editor UI is only ever seen through WebRTC. The Replicator capture reads
# the viewport directly, so hiding it costs the compatibility path nothing.
_hide_ui = ARGS.hide_ui if ARGS.hide_ui is not None else (not ARGS.livestream)

CONFIG = {
    "width": max(160, _render_w),
    "height": max(120, _render_h),
    "window_width": 1920,
    "window_height": 1080,
    "headless": True,
    "hide_ui": _hide_ui,
    "renderer": "RaytracedLighting",
}
if ARGS.multi_gpu is not None:
    CONFIG["multi_gpu"] = bool(ARGS.multi_gpu)
if ARGS.gpu >= 0:
    CONFIG["active_gpu"] = ARGS.gpu
    CONFIG["physics_gpu"] = ARGS.gpu
    CONFIG["multi_gpu"] = False
kit = SimulationApp(launch_config=CONFIG)

import numpy as np
import omni.kit.app
import omni.timeline
import omni.usd
from pxr import Usd


def enable_extension(ext_id: str) -> None:
    try:
        from isaacsim.core.experimental.utils.app import enable_extension as _enable
        _enable(ext_id)
    except Exception:
        manager = omni.kit.app.get_app().get_extension_manager()
        manager.set_extension_enabled_immediate(ext_id, True)


if ARGS.livestream:
    kit.set_setting("/app/window/drawMouse", True)
    kit.set_setting("/exts/omni.kit.livestream.app/primaryStream/publicIp", ARGS.public_ip)
    kit.set_setting("/exts/omni.kit.livestream.app/primaryStream/signalPort", ARGS.signal_port)
    kit.set_setting("/exts/omni.kit.livestream.app/primaryStream/streamPort", ARGS.stream_port)
    kit.set_setting("/exts/omni.kit.livestream.app/primaryStream/streamType", "webrtc")
    kit.set_setting("/exts/omni.kit.livestream.app/primaryStream/targetFps", int(os.environ.get("ISAAC_STREAM_FPS", "60")))
    kit.set_setting("/exts/omni.kit.livestream.app/primaryStream/enableEventTracing", False)
    # 5.x aliases.
    kit.set_setting("/app/livestream/publicEndpointAddress", ARGS.public_ip)
    kit.set_setting("/app/livestream/port", ARGS.signal_port)
    enable_extension("omni.kit.livestream.app")
    for _ in range(5):
        kit.update()
else:
    # Not drawing a cursor nobody will see, and not paying for an encoder
    # session that has no consumer.
    kit.set_setting("/app/window/drawMouse", False)
    for _ in range(2):
        kit.update()

print(f"[stage2] render={CONFIG['width']}x{CONFIG['height']} hide_ui={CONFIG['hide_ui']} "
      f"livestream={'on' if ARGS.livestream else 'off'} "
      f"multi_gpu={CONFIG.get('multi_gpu', 'default')} gpu={CONFIG.get('active_gpu', 'default')}", flush=True)

try:
    from isaacsim.core.utils.stage import is_stage_loading, open_stage
except ImportError:
    from isaacsim.core.experimental.utils.stage import is_stage_loading, open_stage

from isaacsim.storage.native import get_assets_root_path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = Path(ARGS.catalog_dir).expanduser().resolve() if ARGS.catalog_dir else ROOT / "configs"
UPLOAD_DIR = Path(ARGS.upload_dir).expanduser().resolve() if ARGS.upload_dir else ROOT / "uploads"
