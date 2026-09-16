#!/usr/bin/env python3
"""Measure what the playground actually costs, instead of reasoning about it.

Run this ON the machine with the GPUs. It samples nvidia-smi while driving the
playground itself: opening and closing viewers, changing the stream resolution
through the live settings endpoint, and reporting a table.

    python measure_trim.py --server http://127.0.0.1:8080

Every trim in docs/operations/performance-tuning.md was reasoned from what the setting controls, not
observed. This is the tool that turns those into numbers -- including the two
questions that reasoning cannot answer:

  * does an extra viewer cost the GPU anything, or does the shared capture
    loop really make it free?
  * does the stream resolution move the GPU at all, or only the network?

Standard library only.
"""

from __future__ import annotations

import argparse
import http.client
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

GPU_FIELDS = ["index", "name", "utilization.gpu", "memory.used"]


# --- sampling ---------------------------------------------------------------


def nvidia_smi_rows() -> list[dict]:
    binary = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if not binary:
        raise SystemExit("nvidia-smi is not on PATH. Run this on the machine with the GPU.")
    out = subprocess.run(
        [binary, f"--query-gpu={','.join(GPU_FIELDS)}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=20,
    )
    if out.returncode != 0:
        raise SystemExit(f"nvidia-smi failed: {out.stderr.strip() or out.returncode}")
    rows = []
    for line in out.stdout.strip().splitlines():
        if line.strip():
            rows.append(dict(zip(GPU_FIELDS, [p.strip() for p in line.split(",")])))
    return rows


def number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def sample(seconds: float, interval: float = 0.5) -> dict:
    """Average utilisation and memory per GPU over a window."""
    series: dict[str, dict[str, list]] = {}
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for row in nvidia_smi_rows():
            entry = series.setdefault(row["index"], {"name": row["name"], "util": [], "mem": []})
            entry["util"].append(number(row["utilization.gpu"]))
            entry["mem"].append(number(row["memory.used"]))
        time.sleep(interval)
    return {
        index: {
            "name": entry["name"],
            "util": round(statistics.fmean(entry["util"] or [0]), 1),
            "mem": round(statistics.fmean(entry["mem"] or [0]), 0),
        }
        for index, entry in sorted(series.items())
    }


# --- driving the playground -------------------------------------------------


class Client:
    def __init__(self, base: str):
        parsed = urlparse(base)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=20)
        try:
            payload = json.dumps(body) if body is not None else None
            headers = {"Content-Type": "application/json"} if payload else {}
            conn.request(method, path, payload, headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                return json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return {"raw": raw[:200].decode("utf-8", "replace")}
        finally:
            conn.close()

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body)


class Viewer(threading.Thread):
    """One MJPEG client, exactly like a browser tab."""

    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host, self.port = host, port
        self.stop = threading.Event()
        self.bytes_read = 0

    def run(self) -> None:
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
            conn.request("GET", "/api/stream.mjpg")
            response = conn.getresponse()
            while not self.stop.is_set():
                chunk = response.read(65536)
                if not chunk:
                    break
                self.bytes_read += len(chunk)
        except Exception:
            pass


# --- the experiment ---------------------------------------------------------


def show(label: str, before: dict, after: dict | None = None) -> None:
    print(f"\n  {label}")
    for index, gpu in after.items() if after else before.items():
        base = before.get(index) if after else None
        if base:
            print(f"    GPU {index} {gpu['name'][:28]:<28} "
                  f"util {base['util']:5.1f}% -> {gpu['util']:5.1f}%  ({gpu['util'] - base['util']:+5.1f})   "
                  f"mem {base['mem']:6.0f} -> {gpu['mem']:6.0f} MB  ({gpu['mem'] - base['mem']:+6.0f})")
        else:
            print(f"    GPU {index} {gpu['name'][:28]:<28} util {gpu['util']:5.1f}%   mem {gpu['mem']:6.0f} MB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default="http://127.0.0.1:8080")
    parser.add_argument("--window", type=float, default=15.0, help="seconds per measurement")
    parser.add_argument("--viewers", type=int, default=3, help="how many viewers to test with")
    parser.add_argument("--out", help="write the results as JSON")
    args = parser.parse_args()

    client = Client(args.server)
    parsed = urlparse(args.server)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 80

    try:
        original = client.get("/api/stream/settings")
        if not original.get("ok"):
            raise SystemExit(f"the playground did not answer: {original}")
    except OSError as exc:
        raise SystemExit(f"cannot reach {args.server}: {exc}")

    bridge = client.get("/api/status").get("bridge", {}).get("result", {})
    render = bridge.get("render") or {}
    print(f"Isaac render {render.get('width')}x{render.get('height')}  "
          f"hide_ui={render.get('hide_ui')}  multi_gpu={render.get('multi_gpu')}  gpu={render.get('gpu')}")
    print(f"Stream {original['width']}x{original['height']} @ {original['fps']} q={original['quality']}")
    print(f"\nEach measurement takes {args.window:g}s. Total about "
          f"{args.window * (3 + args.viewers) / 60:.1f} minutes.")

    results: dict[str, dict] = {}
    viewers: list[Viewer] = []

    def measure(key: str, label: str) -> dict:
        print(f"\n[{key}] {label} ...", flush=True)
        data = sample(args.window)
        results[key] = data
        return data

    try:
        # 1. Nothing watching. This is what Isaac Sim costs just being alive.
        idle = measure("idle", "no viewers")
        show("idle (no viewers)", idle)

        # 2. Viewers, one at a time. If the shared capture loop works, the
        #    second and third should cost the GPU nothing.
        for n in range(1, args.viewers + 1):
            viewer = Viewer(host, port)
            viewer.start()
            viewers.append(viewer)
            time.sleep(2.0)
            data = measure(f"viewers_{n}", f"{n} viewer(s)")
            show(f"{n} viewer(s)  vs idle", idle, data)

        # 3. Same viewers, a much smaller stream. Isolates whether resolution
        #    costs the GPU or only the network.
        client.post("/api/stream/settings", {"width": 640, "height": 360, "quality": 60})
        time.sleep(3.0)
        small = measure("small_stream", f"{len(viewers)} viewer(s) at 640x360")
        show(f"640x360  vs  {original['width']}x{original['height']} (same viewers)",
             results[f"viewers_{len(viewers)}"], small)

    finally:
        for viewer in viewers:
            viewer.stop.set()
        client.post("/api/stream/settings", {
            "width": original["width"], "height": original["height"],
            "fps": original["fps"], "quality": original["quality"],
        })
        print(f"\nstream restored to {original['width']}x{original['height']} q={original['quality']}")

    print("\n--- what this tells you ---")
    one = results.get("viewers_1", {})
    many = results.get(f"viewers_{args.viewers}", {})
    for index in sorted(idle):
        d_one = one.get(index, {}).get("util", 0) - idle[index]["util"]
        d_many = many.get(index, {}).get("util", 0) - idle[index]["util"]
        d_small = results.get("small_stream", {}).get(index, {}).get("util", 0) - many.get(index, {}).get("util", 0)
        print(f"  GPU {index}: first viewer {d_one:+.1f} points, "
              f"{args.viewers} viewers {d_many:+.1f} points, "
              f"dropping to 640x360 {d_small:+.1f} points")
    print("  If viewers 2 and 3 are near zero, the shared capture loop is doing its job.")
    print("  If 640x360 barely moves the GPU, resolution is a network cost, not a GPU one --")
    print("  in which case trimming it hurt the picture for nothing.")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
