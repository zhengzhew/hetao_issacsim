"""Start the selected station inside the Isaac Sim container."""
import json
import os
from pathlib import Path


def command(config, station_id, root, env):
    station = next((s for s in config["stations"] if s["id"] == station_id), None)
    if station is None:
        raise ValueError("ISAAC_STATION_ID must identify a configured station")
    data = Path(env.get("ISAAC_PLATFORM_DATA_DIR", "/data/stations"))
    uploads = data / station["id"] / "uploads"
    if not (uploads / "challenges").is_dir():
        raise ValueError("Challenge assets are not ready; start the worker first")
    stream_host = station.get("streamHost") or env.get("ISAAC_STREAM_HOST", "127.0.0.1")
    env.update({
        "ISAAC_UPLOAD_DIR": str(uploads), "ISAAC_CATALOG_DIR": str(root / "configs"),
        "ISAAC_DEFAULT_SCENE": "challenge-arm", "ISAAC_DEFAULT_ROBOT": "so101",
        "ISAAC_PUBLIC_IP": station.get("publicIp") or env.get("ISAAC_PUBLIC_IP") or stream_host,
        "ISAAC_SIGNAL_PORT": str(station["signalPort"]), "ISAAC_MEDIA_PORT": str(station["mediaPort"]),
        "ISAAC_RENDER_WIDTH": str(station.get("width", 1920)),
        "ISAAC_RENDER_HEIGHT": str(station.get("height", 1080)),
        "ISAAC_STREAM_FPS": str(env.get("ISAAC_STREAM_FPS") or station.get("fps", 30)),
    })
    # Docker exposes the selected physical card as device 0 inside this container.
    return [str(Path(env.get("ISAAC_DIR", "/isaac-sim")) / "python.sh"),
            str(root / "bridge/isaac_playground.py"),
            "--host", station.get("bridgeHost", "127.0.0.1"),
            "--port", str(station["bridgePort"]), "--livestream", "--hide-ui",
            "--idle-after", "0", "--no-multi-gpu", "--gpu", "0"]


if __name__ == "__main__":
    with open(os.environ["ISAAC_PLATFORM_CONFIG"], encoding="utf-8") as handle:
        config = json.load(handle)
    args = command(config, os.environ["ISAAC_STATION_ID"], Path(__file__).resolve().parents[2], os.environ)
    os.execv(args[0], args)
