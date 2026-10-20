"""Read-only health probe for the actual Isaac simulation loop, not Kit log paths."""
import json
import os
from pathlib import Path
import socket
import sys
import time


def ready(reply):
    result = reply.get("result") or {}
    return (reply.get("ok") is True and result.get("mock") is False
            and result.get("session", {}).get("status") == "ready"
            and result.get("stream", {}).get("livestream") is True)


def probe(config, station_id):
    station = next(s for s in config["stations"] if s["id"] == station_id)
    request = {"id": "health", "op": "ping", "args": {}, "expiresAt": time.time() * 1000 + 4500}
    with socket.create_connection((station.get("bridgeHost", "127.0.0.1"), station["bridgePort"]), timeout=5) as connection:
        connection.sendall((json.dumps(request) + "\n").encode())
        with connection.makefile("rb") as stream:
            line = stream.readline(262145)
        if len(line) > 262144 or not line.endswith(b"\n"):
            raise ValueError("Incomplete or oversized simulation health response")
        reply = json.loads(line)
        if reply.get("id") != "health" or not ready(reply):
            raise ValueError("Simulation scene or streaming is not ready")


if __name__ == "__main__":
    try:
        config = json.loads(Path(os.environ["ISAAC_PLATFORM_CONFIG"]).read_text(encoding="utf-8"))
        probe(config, os.environ["ISAAC_STATION_ID"])
    except (OSError, ValueError, KeyError, StopIteration, TypeError, AttributeError) as error:
        print("Simulation health check failed: " + str(error), file=sys.stderr)
        sys.exit(1)
