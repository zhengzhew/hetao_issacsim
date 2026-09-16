#!/usr/bin/env python3
"""Isaac Web Playground bridge -- entrypoint (no-duck build).

Runs inside Isaac Sim. Boots the SimulationApp (core.app_context), starts the
TCP control server, launches the initial scene + robot, and runs the main
update loop until Kit exits. All behaviour lives in core/*; this file is only
process wiring and the main loop.
"""
from __future__ import annotations

import threading
import time
import traceback

from core.app_context import ARGS, kit
from core import session
from core.net import (
    Handler, Server, drain, enforce_teleop_watchdog, enforce_watchdog,
    launch_session, note_loop_timing, throttle_when_idle,
)

server = Server((ARGS.host, ARGS.port), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
print(
    f"[stage2] READY bridge={ARGS.host}:{ARGS.port} public_ip={ARGS.public_ip} "
    f"signal={ARGS.signal_port}/tcp media={ARGS.stream_port}/udp watchdog={ARGS.watchdog}s",
    flush=True,
)

# Initial session is launched after the TCP server exists, on the main Kit thread.
try:
    launch_session(ARGS.scene_id, ARGS.robot_id)
except Exception:
    traceback.print_exc()

try:
    while kit.is_running() and not kit.is_exiting():
        _t0 = time.perf_counter()
        drain()
        _t1 = time.perf_counter()
        enforce_watchdog()
        enforce_teleop_watchdog()
        _t2 = time.perf_counter()
        kit.update()
        _t3 = time.perf_counter()
        note_loop_timing(_t1 - _t0, _t2 - _t1, _t3 - _t2)
        throttle_when_idle()
finally:
    try:
        session.ROBOT.stop()
    except Exception:
        pass
    server.shutdown()
    kit.close()
