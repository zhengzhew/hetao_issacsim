"""Two-disk layout for the 50 GB system disk and 70 GB /data disk."""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess

GIB = 1024 ** 3
DOCKER_ROOT = Path("/data/docker")


def run(*args, **kwargs):
    print("+ " + " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def existing_parent(path):
    while not path.exists():
        path = path.parent
    return path


def check_space(app, state, docker_root=DOCKER_ROOT, fresh=True):
    # Build budgets, not a guarantee of future image/cache sizes. Sum requirements
    # per actual filesystem rather than pretending free space across disks is fungible.
    mount = docker_root.parent
    if not mount.is_mount() or mount.is_symlink():
        raise RuntimeError(f"{mount} must be a mounted data disk; refusing to fill the system disk")
    groups = {}
    for path, budget in [(app, 2 if fresh else 1), (state, 10 if fresh else 5),
                         (docker_root, 45 if fresh else 8)]:
        parent = existing_parent(path)
        device = parent.stat().st_dev
        group = groups.setdefault(device, {"path": parent, "required": 0, "paths": []})
        group["required"] += budget
        group["paths"].append(str(path))
    for group in groups.values():
        free = shutil.disk_usage(group["path"]).free / GIB
        print(f"Disk {', '.join(group['paths'])}: {free:.1f} GiB free; budget {group['required']} GiB")
        if free < group["required"]:
            raise RuntimeError("Insufficient free space on " + str(group["path"]) +
                               "; inspect docker system df and application caches; no data was deleted")


def daemon_config(original, docker_root=DOCKER_ROOT):
    result = copy.deepcopy(original)
    result["data-root"] = str(docker_root)
    result["storage-driver"] = "overlay2"
    # Docker 29's containerd store retains compressed AND extracted layers,
    # and its storage is not moved by data-root. Select classic storage explicitly.
    result.setdefault("features", {})["containerd-snapshotter"] = False
    result.setdefault("builder", {})["gc"] = {"enabled": True, "defaultKeepStorage": "4GB"}
    return result


def configure_docker(config_file=Path("/etc/docker/daemon.json"), docker_root=DOCKER_ROOT):
    original = json.loads(config_file.read_text()) if config_file.exists() else {}
    updated = daemon_config(original, docker_root)
    if original == updated:
        return False
    if shutil.which("docker"):
        info = subprocess.run(["docker", "info", "--format", "{{json .}}"],
                              capture_output=True, text=True)
        if info.returncode == 0:
            report = json.loads(info.stdout)
            if report.get("Images", 0) or report.get("Containers", 0):
                raise RuntimeError("Existing Docker images/containers found. Do not switch their storage automatically; "
                                   "review daemon.json and migrate deliberately before retrying")
    # An offline daemon may also have data: changing settings would hide it.
    for directory in {Path(original.get("data-root", "/var/lib/docker")), docker_root,
                      Path("/var/lib/containerd")}:
        if directory.exists() and any(directory.iterdir()):
            raise RuntimeError(f"Existing storage at {directory}; no automatic migration or deletion")
    docker_root.mkdir(parents=True, exist_ok=True)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    if config_file.exists():
        backup = config_file.with_suffix(".before-hetao.json")
        if not backup.exists():
            shutil.copy2(config_file, backup)
    temporary = config_file.with_suffix(".new")
    temporary.write_text(json.dumps(updated, indent=2) + "\n")
    run("dockerd", "--validate", "--config-file", temporary)
    temporary.replace(config_file)
    return True


def verify_docker(docker_root=DOCKER_ROOT):
    report = json.loads(run("docker", "info", "--format", "{{json .}}",
                            capture_output=True, text=True).stdout)
    if Path(report["DockerRootDir"]).resolve() != docker_root.resolve() or report["Driver"] != "overlay2":
        raise RuntimeError("Docker must use /data/docker and classic overlay2 before pulling Isaac Sim")


def has_base_image(image="nvcr.io/nvidia/isaac-sim:6.0.1"):
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", image],
                          capture_output=True, text=True).returncode == 0


def image_ids(tag):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", tag):
        raise ValueError("Invalid project image tag")
    result = {}
    for name in (f"hetao-isaac-web:{tag}", f"hetao-isaac-sim:{tag}"):
        reply = subprocess.run(["docker", "image", "inspect", name, "--format", "{{.Id}}"],
                               capture_output=True, text=True)
        if reply.returncode == 0:
            result[name] = reply.stdout.strip()
    return result


def remove_replaced_images(previous, tag):
    # Only superseded images from these two exact tags. Never prune all Docker data.
    current = image_ids(tag)
    for name, image_id in previous.items():
        if name not in current:
            reply = subprocess.run(["docker", "image", "inspect", name, "--format", "{{.Id}}"],
                                   capture_output=True, text=True)
            if reply.returncode == 0 and reply.stdout.strip() == image_id:
                subprocess.run(["docker", "image", "rm", name], check=False)  # No --force; in-use images survive.
