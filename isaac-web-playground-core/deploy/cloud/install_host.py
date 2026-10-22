"""Deploy this GitHub checkout locally on TencentOS 4, using the existing two disks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

import host_dependencies as dependencies
import host_runtime as runtime
import host_storage as storage
import manage

APP = Path("/opt/hetao-isaac")
DATA = Path("/srv/hetao-isaac")
UNIT = "hetao-isaac.service"
ROOT = Path(__file__).resolve().parents[2]
run = storage.run


def source_tag(root=ROOT):
    # A content tag also handles deliberate local source edits. Never include
    # private configs, uploaded assets or generated runtime files in this hash.
    digest = hashlib.sha256()
    files = [root / n for n in ("package.json", "package-lock.json", ".dockerignore")]
    for folder in ("server", "src", "web", "bridge", "third_party", "deploy/cloud"):
        files.extend(p for p in (root / folder).rglob("*") if p.is_file() and not p.is_symlink())
    files.extend(root / "configs" / n for n in ("scenes.json", "robots.json", "challenges.json", "challenge-assets.lock.json"))
    files.extend(root / "scripts" / n for n in ("build_native.mjs", "fetch_challenge_assets.py"))
    for file in sorted(set(files)):
        rel = file.relative_to(root)
        if "__pycache__" in rel.parts or rel.parts[:2] == ("web", "downloads") or file.name.startswith("native-sdk.js"):
            continue
        digest.update(rel.as_posix().encode() + b"\0" + file.read_bytes())
    return digest.hexdigest()[:16]


def read_env(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))


def update_env(path, changes):
    remaining = dict(changes)
    result = []
    for line in path.read_text().splitlines():
        key = line.split("=", 1)[0]
        result.append(f"{key}={remaining.pop(key)}" if key in remaining else line)
    result.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(result) + "\n")


def selected_ip(argument, directory=DATA):
    if argument:
        return runtime.public_ip(argument)
    config = directory / "host.json"
    if config.exists():
        return runtime.public_ip(json.loads(config.read_text())["publicIp"])
    raise ValueError("First install requires --public-ip <this server's reachable public IPv4>")


def install(args):
    import fcntl
    if os.geteuid() != 0:
        raise RuntimeError("Run with sudo")
    dependencies.check_os()
    address = selected_ip(args.public_ip)
    if not args.accept_eula:
        raise ValueError("Read the NVIDIA Isaac Sim terms, then pass --accept-eula")
    if any(c.isspace() for c in str(ROOT)):
        raise ValueError("Clone the repository into a path without spaces, for example /opt/hetao-isaac/repo")
    current = APP / "current"
    if current.exists() and not current.is_symlink():
        raise ValueError(f"{current} must be a managed symlink")
    APP.mkdir(parents=True, exist_ok=True)
    with (APP / "install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fresh = not (DATA / ".env").exists()
        base_image = (read_env(DATA / ".env").get("ISAAC_SIM_IMAGE", "nvcr.io/nvidia/isaac-sim:6.0.1")
                      if not fresh else "nvcr.io/nvidia/isaac-sim:6.0.1")
        storage.check_space(APP, DATA, fresh=not storage.has_base_image(base_image))
        if args.install_driver:
            dependencies.install_driver()
        dependencies.check_gpu()
        dependencies.prepare()
        if fresh:
            manage.initialize(DATA, "10.0.0.1", accept_eula=True)
            update_env(DATA / ".env", {
                "NODE_IMAGE": "public.ecr.aws/docker/library/node:22-bookworm-slim",
                "PYTHON_IMAGE": "public.ecr.aws/docker/library/python:3.12-slim-bookworm",
                "CADDY_IMAGE": "public.ecr.aws/docker/library/caddy:2.11.7",
            })
        previous = storage.image_ids(read_env(DATA / ".env").get("RELEASE_TAG", "cloud-local"))
        tag = source_tag()
        # Build before stopping the running service. A failed build must not
        # leave the installed .env pointing at an unbuilt image tag.
        candidate = APP / "build.env"
        candidate.write_text((DATA / ".env").read_text())
        candidate.chmod(0o600)
        update_env(candidate, {"RELEASE_TAG": tag, "ACCEPT_EULA": "Y"})
        compose = ["docker", "compose", "--parallel", "1", "--env-file", str(candidate),
                   "-f", str(ROOT / "deploy/cloud/compose.yaml"),
                   "-f", str(ROOT / "deploy/cloud/compose.public.yaml")]
        run(*compose, "pull", "edge")
        # Keep one explicit base tag: shared overlay2 layers remain reusable,
        # and later preflights can distinguish a cold pull from a warm update.
        run("docker", "pull", base_image)
        storage.check_space(APP, DATA, fresh=False)
        run(*compose, "build", "gateway")
        storage.check_space(APP, DATA, fresh=False)
        run(*compose, "build", "sim")
        storage.check_space(APP, DATA, fresh=False)
        if Path("/etc/systemd/system/" + UNIT).exists():
            run("systemctl", "stop", UNIT)
        run(*manage.compose_command(DATA), "down", "--timeout", "60")
        runtime.write_private(DATA / "host.json", json.dumps({"publicIp": address}) + "\n")
        runtime.update_identity(DATA, runtime.configured_identity(DATA))
        runtime.initialize_teacher(DATA, secrets.token_urlsafe(18))
        update_env(DATA / ".env", {"RELEASE_TAG": tag, "ACCEPT_EULA": "Y"})
        candidate.unlink()
        runtime.write_private(DATA / "boot-managed", "systemd\n")
        replacement = APP / "current.new"
        if replacement.is_symlink():
            replacement.unlink()
        replacement.symlink_to(ROOT, target_is_directory=True)
        replacement.replace(current)
        shutil.copyfile(ROOT / "deploy/cloud/hetao-isaac.service", "/etc/systemd/system/" + UNIT)
        run("systemctl", "daemon-reload")
        run("systemctl", "enable", UNIT)
        run("systemctl", "restart", UNIT)
        run("systemctl", "is-active", "--quiet", UNIT)
        result = json.loads((DATA / "startup-status.json").read_text())
        if result["phase"] != "scene-ready":
            raise RuntimeError("Startup did not reach real scene readiness")
        storage.remove_replaced_images(previous, tag)
        print(f"Scene ready. Open https://{address}/ and verify real browser video and controls.")
        print(f"Teacher password: sudo cat {DATA}/state/platform/teacher-password.txt")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-ip", help="Public IPv4; saved for later boots/updates")
    parser.add_argument("--accept-eula", action="store_true")
    parser.add_argument("--install-driver", action="store_true", help="Install TencentOS 580 driver if absent; never reboot")
    parser.add_argument("--check", action="store_true", help="Read-only OS, space, GPU and runtime check")
    args = parser.parse_args(argv)
    if args.check:
        dependencies.check_os()
        print("Public IP:", selected_ip(args.public_ip))
        base_image = (read_env(DATA / ".env").get("ISAAC_SIM_IMAGE", "nvcr.io/nvidia/isaac-sim:6.0.1")
                      if (DATA / ".env").exists() else "nvcr.io/nvidia/isaac-sim:6.0.1")
        storage.check_space(APP, DATA, fresh=not storage.has_base_image(base_image))
        dependencies.check_gpu()
        for command in (["docker", "compose", "version"], ["docker", "buildx", "version"]):
            run(*command)
        storage.verify_docker()
        print("Host preflight passed; rendering, certificate and browser video still require acceptance.")
        return 0
    install(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
