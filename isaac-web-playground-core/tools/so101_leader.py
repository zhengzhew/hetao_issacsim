#!/usr/bin/env python3
"""Stream a leader arm into the Isaac Web Playground.

The leader arm is physical hardware on a serial port, so it has to be read on
whatever machine it is plugged into -- which is usually not the machine running
Isaac Sim. This script is that reader. It talks to the playground over plain
HTTP on the port the web page already uses, so the arm can sit on your desk
while the simulation runs in the server room.

    # real SO-101 leader
    python3 so101_leader.py --server http://<host-ip>:8080 --port /dev/ttyACM0

    # no hardware: drive the follower with a generated trajectory
    python3 so101_leader.py --server http://<host-ip>:8080 --simulate

    # capture the current pose as the zero point and save a mapping
    python3 so101_leader.py --port /dev/ttyACM0 --write-calibration leader.json

Only the standard library is required. lerobot is imported lazily and only when
a real port is given.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import signal
import sys
import time
import queue
import threading
from collections import deque
from urllib.parse import urlparse

SO101_JOINTS = ["Rotation", "Pitch", "Elbow", "Wrist_Pitch", "Wrist_Roll", "Jaw"]


# --- leader sources ---------------------------------------------------------


class SimulatedLeader:
    """A smooth, bounded trajectory. Lets the whole path be tested with no arm."""

    name = "simulated"

    def __init__(self, joints: list[str], amplitude: float = 0.6, period: float = 8.0):
        self.joints = joints
        self.amplitude = amplitude
        self.period = period
        self.started = time.monotonic()

    def connect(self) -> None:
        print(f"[leader] simulated source, {len(self.joints)} joints, "
              f"±{self.amplitude} rad over {self.period}s")

    def read(self) -> dict:
        t = time.monotonic() - self.started
        return {
            name: self.amplitude * math.sin(2 * math.pi * (t / self.period) + index * 0.7)
            for index, name in enumerate(self.joints)
        }

    def close(self) -> None:
        pass


class SO101Leader:
    """The real arm, through lerobot's SO-101 teleoperator driver."""

    name = "so101"

    def __init__(self, port: str, arm_id: str):
        self.port = port
        self.arm_id = arm_id
        self.device = None

    def connect(self) -> None:
        try:
            from lerobot.teleoperators.so101_leader import SO101Leader as Driver
            from lerobot.teleoperators.so101_leader import SO101LeaderConfig
        except ImportError as exc:
            raise SystemExit(
                f"lerobot is not installed in this Python ({exc}).\n"
                "Install it on the machine the arm is plugged into, or use --simulate."
            )
        self.device = Driver(SO101LeaderConfig(port=self.port, id=self.arm_id))
        self.device.connect()
        print(f"[leader] connected to SO-101 on {self.port} as {self.arm_id}")

    def read(self) -> dict:
        action = self.device.get_action()
        # lerobot names them "<joint>.pos"; the playground wants bare names.
        return {
            str(key).split(".")[0]: float(value)
            for key, value in action.items()
            if isinstance(value, (int, float))
        }

    def close(self) -> None:
        try:
            if self.device is not None:
                self.device.disconnect()
        except Exception:
            pass


# --- playground client ------------------------------------------------------


class Playground:
    """One keep-alive HTTP connection; reconnects on its own."""

    def __init__(self, base_url: str, timeout: float = 2.0):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise SystemExit(f"--server must be an http(s) URL, got {base_url!r}")
        self.secure = parsed.scheme == "https"
        self.host = parsed.hostname
        self.port = parsed.port or (443 if self.secure else 80)
        self.timeout = timeout
        self.conn = None

    def _connect(self):
        cls = http.client.HTTPSConnection if self.secure else http.client.HTTPConnection
        self.conn = cls(self.host, self.port, timeout=self.timeout)

    def post(self, path: str, payload: dict) -> tuple[int, dict]:
        body = json.dumps(payload)
        for attempt in (1, 2):
            try:
                if self.conn is None:
                    self._connect()
                self.conn.request("POST", path, body, {"Content-Type": "application/json"})
                response = self.conn.getresponse()
                raw = response.read()
                try:
                    return response.status, json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    return response.status, {"error": raw[:200].decode("utf-8", "replace")}
            except (http.client.HTTPException, OSError) as exc:
                try:
                    if self.conn:
                        self.conn.close()
                except Exception:
                    pass
                self.conn = None
                if attempt == 2:
                    raise ConnectionError(f"{path}: {exc}") from exc
        raise AssertionError("unreachable")

    def close(self) -> None:
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass


# --- calibration ------------------------------------------------------------


UNIT_SCALE = {"rad": 1.0, "deg": math.pi / 180.0, "raw": 1.0}


def parse_map(text: str) -> dict:
    """--map follower=leader,follower=leader"""
    mapping = {}
    for pair in str(text or "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise SystemExit(f"--map entries look like follower=leader, got {pair!r}")
        follower, leader = (part.strip() for part in pair.split("=", 1))
        if not follower or not leader:
            raise SystemExit(f"--map entry is incomplete: {pair!r}")
        mapping[follower] = leader
    return mapping


def build_calibration(zero_sample: dict, follower_joints: list[str], name_map: dict,
                      scale: float, unit: str, invert: list[str]) -> dict:
    """Build {follower_joint: {source: leader_joint, ...}}.

    The keys are FOLLOWER joint names and `source` is the LEADER name -- that is
    what the bridge expects. Getting this backwards silently produces a session
    where every sample is rejected, so the direction is worth being explicit
    about.

    `offset` is the leader's reading right now, so the follower starts from
    where it already is instead of jumping.
    """
    unit_scale = UNIT_SCALE.get(unit, 1.0)
    mapping = {}
    for follower in follower_joints:
        leader = name_map.get(follower, follower)
        if leader not in zero_sample:
            continue
        mapping[follower] = {
            "source": leader,
            "offset": round(float(zero_sample[leader]), 6),
            "scale": scale * unit_scale,
            "invert": follower in invert or leader in invert,
        }
    return mapping


# --- main -------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default="http://127.0.0.1:8080", help="playground base URL")
    parser.add_argument("--port", help="leader arm serial port, e.g. /dev/ttyACM0 or COM3")
    parser.add_argument("--id", default="leader_arm_1", help="lerobot arm id")
    parser.add_argument("--simulate", action="store_true", help="generate motion instead of reading hardware")
    parser.add_argument("--rate", type=float, default=30.0, help="samples per second (default 30)")
    parser.add_argument("--joints", default=",".join(SO101_JOINTS), help="joint names for --simulate")
    parser.add_argument("--scale", type=float, default=1.0, help="extra leader-to-follower scale factor")
    parser.add_argument("--unit", choices=sorted(UNIT_SCALE), default="rad",
                        help="units the leader reports: rad, deg, or raw (no conversion)")
    parser.add_argument("--map", dest="name_map", default="",
                        help="follower=leader name pairs, e.g. Rotation=shoulder_pan,Jaw=gripper")
    parser.add_argument("--invert", default="", help="comma separated joints to invert")
    parser.add_argument("--calibration", help="load a calibration JSON instead of auto-zeroing")
    parser.add_argument("--write-calibration", help="capture the current pose as zero, write it here and exit")
    parser.add_argument("--no-zero", action="store_true", help="send raw leader values with no calibration")
    parser.add_argument("--connections", type=int, default=4,
                        help="parallel connections; one request at a time caps the rate at 1/RTT")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.simulate and not args.port:
        parser.error("give --port for a real arm, or --simulate to run without one")
    if args.rate <= 0 or args.rate > 200:
        parser.error("--rate must be between 0 and 200")
    if args.scale == 0:
        parser.error("--scale cannot be zero")
    if not 1 <= args.connections <= 16:
        parser.error("--connections must be between 1 and 16")
    if args.port and "--unit" not in sys.argv:
        parser.error("--unit is required with --port: lerobot does not report radians, "
                     "and guessing drives the follower into its limits. "
                     "Use --unit deg, --unit raw with --scale, or --unit rad if you are sure.")

    joints = [j.strip() for j in args.joints.split(",") if j.strip()]
    invert = [j.strip() for j in args.invert.split(",") if j.strip()]
    leader = SimulatedLeader(joints) if args.simulate else SO101Leader(args.port, args.id)
    leader.connect()

    first = leader.read()
    if not first:
        print("[leader] the source returned no joints", file=sys.stderr)
        return 2
    print(f"[leader] joints: {', '.join(sorted(first))}")

    name_map = parse_map(args.name_map)

    if args.write_calibration:
        mapping = build_calibration(first, list(first), name_map, args.scale, args.unit, invert)
        with open(args.write_calibration, "w", encoding="utf-8") as handle:
            json.dump({"calibration": mapping}, handle, indent=2)
        print(f"[leader] wrote {args.write_calibration} with {len(mapping)} joints zeroed at the current pose")
        print("[leader] keys are FOLLOWER joint names; edit `source` if the arm in the "
              "playground names its joints differently")
        leader.close()
        return 0

    client = Playground(args.server)

    # Engage first so the follower can tell us its joint names, then calibrate
    # against those. Building the map from the leader's own names is how you end
    # up with a session where every sample is silently rejected.
    status, payload = client.post("/api/teleop/engage", {"source": f"{leader.name}:{args.port or 'sim'}"})
    if status != 200 or not payload.get("ok"):
        print(f"[leader] could not engage teleop: {payload.get('error', status)}", file=sys.stderr)
        leader.close()
        return 3
    teleop = payload.get("teleop", {})
    token = teleop.get("token")
    follower = teleop.get("follower_joints") or []
    print(f"[leader] engaged. follower joints: {', '.join(follower) or '(none reported)'}")
    print(f"[leader] follower slew limit: {teleop.get('max_step')} per sample")

    if args.calibration:
        with open(args.calibration, encoding="utf-8") as handle:
            loaded = json.load(handle)
        calibration = loaded.get("calibration", loaded)
    elif args.no_zero:
        calibration = None
    else:
        calibration = build_calibration(first, follower or list(first), name_map,
                                        args.scale, args.unit, invert)
        print(f"[leader] auto-zeroed at the current pose ({len(calibration)} joints, unit={args.unit})")

    if calibration:
        payload_body = {"calibration": calibration}
        if token:
            payload_body["token"] = token
        status, payload = client.post("/api/teleop/calibrate", payload_body)
        if status != 200 or not payload.get("ok"):
            print(f"[leader] calibration rejected: {payload.get('error', status)}", file=sys.stderr)
            client.post("/api/teleop/disengage", {"token": token})
            leader.close()
            return 4
        matched = sorted(set(calibration) & set(follower)) if follower else list(calibration)
    else:
        matched = sorted(set(first) & set(follower)) if follower else []

    if not follower:
        print("[leader] the playground did not report any follower joints. Load a "
              "joint-driven robot (an arm) in the page first.", file=sys.stderr)
        client.post("/api/teleop/disengage", {"token": token} if token else {})
        leader.close()
        return 5
    if not matched:
        print("[leader] no leader joint maps onto a follower joint. Follower has: "
              f"{', '.join(follower)}; leader reports: {', '.join(sorted(first))}.\n"
              "         Map them with --map follower=leader,... and try again.", file=sys.stderr)
        client.post("/api/teleop/disengage", {"token": token})
        leader.close()
        return 5
    print(f"[leader] driving {len(matched)} joint(s): {', '.join(matched)}")

    running = True

    def stop(_sig, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    try:
        signal.signal(signal.SIGTERM, stop)
    except (AttributeError, ValueError):
        pass

    read_failed = False
    interval = 1.0 / args.rate
    seq = 0
    sent = applied = failed = raced = 0
    latencies: deque[float] = deque(maxlen=120)
    bridge_ms: deque[float] = deque(maxlen=120)
    backoff_until = 0.0
    disengaged_notified = False

    # One request at a time caps the rate at 1/RTT -- about 7 Hz on a link with
    # a 140 ms round trip, which makes the arm step rather than follow.
    # Overlapping sends fixes the rate. The lag is the link's and cannot be
    # fixed here.
    #
    # Deliberately NOT a queue: buffering samples adds their wait time to the
    # control lag, which is the one thing teleoperation cannot afford. There is
    # a single slot holding the newest pose; a sender takes whatever is current
    # when it becomes free, and anything the producer wrote in the meantime is
    # simply overwritten. Dropping an old pose costs nothing -- a newer one is
    # already on its way.
    latest = {"seq": 0, "sample": None, "at": 0.0}
    claimed_seq = 0
    slot = threading.Condition()
    stats_lock = threading.Lock()
    stop_senders = threading.Event()
    dropped_stale = 0

    def sender(worker_id: int) -> None:
        nonlocal sent, applied, failed, raced, backoff_until, disengaged_notified, running, claimed_seq
        conn = Playground(args.server)
        try:
            while not stop_senders.is_set():
                with slot:
                    # Wait until there is a pose nobody has taken yet.
                    while latest["seq"] <= claimed_seq and not stop_senders.is_set():
                        slot.wait(0.2)
                    if stop_senders.is_set():
                        break
                    claimed_seq = latest["seq"]
                    sample_seq = latest["seq"]
                    sample = latest["sample"]
                    queued_at = latest["at"]
                body = {"positions": sample, "seq": sample_seq}
                if token:
                    body["token"] = token
                try:
                    status, payload = conn.post("/api/teleop", body)
                    elapsed = time.monotonic() - queued_at
                    with stats_lock:
                        sent += 1
                        latencies.append(elapsed)
                        if status == 200 and payload.get("applied"):
                            applied += 1
                            disengaged_notified = False
                            if isinstance(payload.get("bridge_ms"), (int, float)):
                                bridge_ms.append(float(payload["bridge_ms"]))
                        elif status == 429:
                            failed += 1
                            backoff_until = time.monotonic() + 0.5
                        else:
                            reason = payload.get("reason") or payload.get("error") or f"HTTP {status}"
                            # Losing the sequence race is expected once several
                            # samples are in flight, and harmless: the newer
                            # pose won. Counting it as a failure reads as a
                            # fault when it is the design working.
                            if "stale" in str(reason):
                                raced += 1
                            else:
                                failed += 1
                            if payload.get("reengage") or "not engaged" in str(reason):
                                if not disengaged_notified:
                                    print(f"[leader] the playground ended this session: {reason}", file=sys.stderr)
                                    disengaged_notified = True
                                running = False
                                stop_senders.set()
                            elif "stale" not in str(reason) and failed in (1, 10, 100):
                                print(f"[leader] sample rejected: {reason}", file=sys.stderr)
                except ConnectionError as exc:
                    with stats_lock:
                        failed += 1
                        backoff_until = time.monotonic() + 0.25
                        if failed % 30 == 1:
                            print(f"[leader] {exc}", file=sys.stderr)
        finally:
            conn.close()

    senders = [threading.Thread(target=sender, args=(i,), daemon=True) for i in range(args.connections)]
    for thread in senders:
        thread.start()
    report_at = time.monotonic() + 2.0
    started_streaming = time.monotonic()
    print(f"[leader] streaming at {args.rate:g} Hz over {args.connections} connection(s). Ctrl+C to stop.")

    try:
        while running:
            cycle_started = time.monotonic()
            try:
                sample = leader.read()
            except Exception as exc:
                print(f"[leader] read failed: {exc}", file=sys.stderr)
                read_failed = True
                break
            if sample and time.monotonic() >= backoff_until:
                seq += 1
                with slot:
                    # Overwriting an unclaimed pose is the point: the newer one
                    # supersedes it and nothing waits in line.
                    if latest["seq"] > claimed_seq:
                        dropped_stale += 1
                    latest.update(seq=seq, sample=sample, at=time.monotonic())
                    slot.notify()

            now = time.monotonic()
            if not args.quiet and now >= report_at:
                window = list(latencies) or [0.0]
                mean_ms = 1000 * sum(window) / len(window)
                p95_ms = 1000 * sorted(window)[int(0.95 * (len(window) - 1))]
                inside = list(bridge_ms) or [0.0]
                inside_mean = sum(inside) / len(inside)
                achieved = applied / max(0.001, now - started_streaming)
                # Splitting these is the difference between "the network is
                # slow" and "the simulator is busy" -- they need opposite fixes.
                print(f"[leader] applied={applied} @ {achieved:.1f}Hz  raced={raced} failed={failed} "
                      f"dropped={dropped_stale}  lag={mean_ms:.0f}ms p95={p95_ms:.0f}ms "
                      f"(bridge {inside_mean:.1f}ms, link {max(0.0, mean_ms - inside_mean):.0f}ms)")
                report_at = now + 2.0

            sleep_for = interval - (time.monotonic() - cycle_started)
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        stop_senders.set()
        with slot:
            slot.notify_all()
        for thread in senders:
            thread.join(timeout=2.0)
        print("\n[leader] disengaging")
        try:
            client.post("/api/teleop/disengage", {"token": token} if token else {})
        except Exception:
            pass
        client.close()
        leader.close()

    print(f"[leader] done. sent={sent} applied={applied} raced={raced} failed={failed}")
    # A hardware read failure is not a clean exit; a supervisor should see it.
    return 6 if read_failed else 0


if __name__ == "__main__":
    sys.exit(main())
