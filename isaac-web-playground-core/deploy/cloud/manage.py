"""Cloud deployment helper. Stopping containers does NOT stop VM billing."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def private_ip(value):
    address = ipaddress.ip_address(value)
    private_ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
    if address.version != 4 or not any(address in ipaddress.ip_network(n) for n in private_ranges):
        raise ValueError("Use a routed VPN/private IPv4 address reachable by store browsers")
    return str(address)


def initialize(directory, host, gpu="0", accept_eula=False):
    host = private_ip(host)
    if not gpu.isdecimal():
        raise ValueError("GPU device must be a numeric host GPU index")
    directory = directory.resolve()
    if any(c in directory.as_posix() for c in "'\r\n"):
        raise ValueError("Deployment directory contains unsupported characters")
    if any((directory / n).exists() for n in ("platform.json", "worker-key", ".env")):
        raise ValueError("Deployment already initialized; edit its config explicitly, do not overwrite credentials")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Choose a new or empty deployment directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    folders = ["state", "state/platform", "state/stations", "cache", "cache/main",
               "cache/compute", "kit-config", "kit-data", "kit-pkg", "logs"]
    for folder in folders:
        (directory / folder).mkdir(parents=True, exist_ok=True, mode=0o700)
    config = {
        "host": host, "port": 8080, "publicOrigin": f"http://{host}:8080", "secureCookies": False,
        "localConnector": {"enabled": False},
        "stations": [{
            "id": "cloud-1", "name": "云端体验台 1", "storeId": "pilot",
            "workerOrigin": "http://127.0.0.1:8081", "webHost": "127.0.0.1",
            "bridgeHost": "127.0.0.1", "signalHost": "127.0.0.1",
            "streamHost": host, "publicIp": host,
            "webPort": 8081, "bridgePort": 8765, "signalPort": 49100, "mediaPort": 47998,
            "gpu": 0, "width": 1920, "height": 1080, "fps": 30,
        }],
    }
    (directory / "platform.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "worker-key").write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    # Compose .env single-quoted values keep spaces and dollar signs literal.
    (directory / ".env").write_text(
        f"DEPLOY_DIR='{directory.as_posix()}'\nGPU_DEVICE={gpu}\nRELEASE_TAG=cloud-local\n"
        "ISAAC_SIM_IMAGE=nvcr.io/nvidia/isaac-sim:6.0.1\n"
        f"ACCEPT_EULA={'Y' if accept_eula else ''}\n", encoding="utf-8")
    for file in ("platform.json", "worker-key", ".env"):
        (directory / file).chmod(0o600)
    if sys.platform == "linux" and os.geteuid() == 0:
        for item in [directory, *directory.rglob("*")]:
            os.chown(item, 1234, 1234)
    return config


def ready_status(status):
    bridge = status.get("bridge", {}).get("result") or {}
    return bool(status.get("nativeBundleAvailable") and status.get("signaling", {}).get("connected") and
                bridge.get("mock") is False and bridge.get("session", {}).get("status") == "ready" and
                bridge.get("stream", {}).get("livestream") is True)


def wait_ready(directory, timeout):
    config = json.loads((directory / "platform.json").read_text(encoding="utf-8"))
    key = (directory / "worker-key").read_text(encoding="utf-8").strip()
    deadline = time.monotonic() + timeout
    last = ""
    while True:
        pending = []
        for station in config["stations"]:
            base = station.get("workerOrigin") or f"http://127.0.0.1:{station['webPort']}"
            try:
                req = Request(base + "/api/status", headers={"X-Isaac-Worker-Key": key})
                with urlopen(req, timeout=5) as response:
                    status = json.load(response)
                if not ready_status(status):
                    pending.append(station["id"] + ": scene/stream not ready")
            except (OSError, ValueError) as error:
                pending.append(station["id"] + ": " + type(error).__name__)
        if not pending:
            print("Scene and signaling ready. Browser video reception/FPS must still be verified.")
            return 0
        message = "; ".join(pending)
        if message != last:
            print(message, flush=True)
            last = message
        if time.monotonic() >= deadline:
            return 1
        time.sleep(min(3, max(0, deadline - time.monotonic())))


def bundle(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Bundle already exists; choose a new output path")
    files = [ROOT / n for n in (".dockerignore", "package.json", "package-lock.json")]
    for folder in ("server", "web", "src", "bridge", "third_party"):
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file())
    files.extend(ROOT / "configs" / n for n in ("scenes.json", "robots.json", "challenges.json", "challenge-assets.lock.json"))
    files.extend(ROOT / "scripts" / n for n in ("build_native.mjs", "fetch_challenge_assets.py"))
    files.extend(p for p in HERE.glob("*") if p.is_file() and p.suffix in (".py", ".mjs", ".yaml", ".md") or
                 p.is_file() and p.name.startswith("Dockerfile."))
    files.append(HERE / "empty-assets/.gitkeep")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "x:gz") as archive:
        for file in sorted(set(files)):
            rel = file.relative_to(ROOT)
            if file.is_symlink() or "__pycache__" in rel.parts or file.suffix == ".pyc":
                continue
            if rel.parts[:2] == ("web", "downloads") or file.name.startswith("native-sdk.js"):
                continue
            if file.name.startswith(".env") or file.suffix in (".env", ".pem", ".key"):
                continue
            archive.add(file, arcname="isaac-web-playground-core/" + rel.as_posix(), recursive=False)
    print(f"Source bundle: {destination}")
    print("Excludes credentials, calibration profiles, uploads, runtime data, node_modules and Git history.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "build", "up", "down", "status", "logs", "ready", "doctor", "bundle"])
    parser.add_argument("--directory", type=Path, default=HERE / "local")
    parser.add_argument("--stream-host", help="VPN IPv4 assigned to this GPU host")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--accept-eula", action="store_true", help="Accept NVIDIA Isaac Sim EULA for this deployment")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    directory = args.directory.resolve()
    if args.action == "bundle":
        if not args.output:
            parser.error("bundle requires --output")
        bundle(args.output)
        return 0
    if args.action == "init":
        if not args.stream_host:
            parser.error("init requires --stream-host")
        if sys.platform == "linux" and os.geteuid() not in (0, 1234):
            parser.error("Run init with sudo so persistent directories can be owned by container UID 1234")
        config = initialize(directory, args.stream_host, args.gpu, args.accept_eula)
        print(f"Initialized {directory}; browser URL {config['publicOrigin']}")
        print("No VM, firewall or network settings changed. Confirm VPN routing before starting.")
        return 0
    if args.action == "ready":
        return wait_ready(directory, max(0, args.timeout))
    if not shutil.which("docker"):
        raise RuntimeError("Docker with the Compose plugin is required on the Linux GPU host")
    if args.action == "doctor":
        for command in (["docker", "compose", "version"], ["docker", "info", "--format", "{{.OSType}}"],
                        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv"]):
            subprocess.run(command, check=True)
        print("Basic host checks only; Vulkan/RTX, NVENC and actual browser video remain to be tested.")
        return 0
    if not (directory / ".env").is_file():
        raise ValueError("Run init first")
    compose = ["docker", "compose", "--env-file", str(directory / ".env"), "-f", str(HERE / "compose.yaml")]
    operations = {"build": ["build"], "up": ["up", "-d", "--build"],
                  "down": ["down", "--timeout", "60"], "status": ["ps", "--all"],
                  "logs": ["logs", "--tail", "100"]}
    subprocess.run(compose + operations[args.action], check=True)
    if args.action == "down":
        print("Containers stopped; persistent data retained. VM billing CONTINUES.")
        print("Use your cloud console/API: stop without compute charges. Verify its billing state.")
    if args.action == "up":
        print("Containers started. Run ready, then verify the picture from a store browser.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
