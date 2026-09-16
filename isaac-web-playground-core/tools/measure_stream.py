#!/usr/bin/env python3
"""Measure the stream as a viewer receives it, not as the server sends it.

Every frame-rate figure taken so far came from the server's own counter, which
says how many frames were captured -- not how many arrived anywhere. A viewer
on the far side of a VPN gets whatever the link can carry, and 1280x720 at
q80 is roughly 150 kB a frame: 25 fps of that is 30 Mbit/s.

Run it on the host and again on the machine actually being used. The gap
between the two is the network, and nothing on the server can show it.

    python3 tools/measure_stream.py http://<host-ip>:8080
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from urllib.parse import urlparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("base", nargs="?", default="http://127.0.0.1:8080")
parser.add_argument("--seconds", type=float, default=15.0)
ARGS = parser.parse_args()

url = urlparse(ARGS.base)
host = url.hostname or "127.0.0.1"
port = url.port or 80

print(f"connecting to {host}:{port} for {ARGS.seconds:g}s", flush=True)
started = time.perf_counter()
sock = socket.create_connection((host, port), 10)
connect_ms = (time.perf_counter() - started) * 1000.0
sock.sendall(f"GET /api/stream.mjpg HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())

# Frames are delimited by the JPEG start-of-image marker. Counting those is
# enough and avoids parsing multipart headers.
MARKER = b"\xff\xd8\xff"
buffer = b""
frames = 0
total = 0
first_frame_ms = None
gaps: list[float] = []
last_at = None

sock.settimeout(ARGS.seconds + 5)
deadline = time.perf_counter() + ARGS.seconds
while time.perf_counter() < deadline:
    try:
        chunk = sock.recv(65536)
    except socket.timeout:
        break
    if not chunk:
        break
    total += len(chunk)
    buffer += chunk
    while True:
        index = buffer.find(MARKER)
        if index < 0:
            break
        buffer = buffer[index + 3:]
        now = time.perf_counter()
        if first_frame_ms is None:
            first_frame_ms = (now - started) * 1000.0
        if last_at is not None:
            gaps.append((now - last_at) * 1000.0)
        last_at = now
        frames += 1
    # Keep the tail short; a partial marker is at most two bytes.
    if len(buffer) > 4:
        buffer = buffer[-2:]
sock.close()

elapsed = time.perf_counter() - started
fps = frames / max(elapsed, 1e-9)
mbit = total * 8 / max(elapsed, 1e-9) / 1e6
print(f"  connect            {connect_ms:6.1f} ms")
print(f"  first frame after  {first_frame_ms or float('nan'):6.1f} ms")
print(f"  frames             {frames} in {elapsed:.1f}s  =  {fps:.1f} fps")
print(f"  bytes              {total / 1e6:.1f} MB  =  {mbit:.1f} Mbit/s")
print(f"  per frame          {total / max(frames, 1) / 1024:.0f} kB")
if gaps:
    gaps.sort()
    print(f"  gap median         {gaps[len(gaps) // 2]:6.1f} ms")
    print(f"  gap worst          {gaps[-1]:6.1f} ms   <- a stutter this long is visible")
    long_gaps = sum(1 for g in gaps if g > 200.0)
    print(f"  gaps over 200 ms   {long_gaps} of {len(gaps)}")
