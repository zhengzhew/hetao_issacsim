"""TencentOS Server 4 RPM prerequisites. No host CUDA Toolkit or Node needed."""
import configparser
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from urllib.request import urlopen

import host_storage as storage

run = storage.run


def validate_toolkit_repo(content):
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(content)
    # NVIDIA signs repository metadata (its official RPM repo uses gpgcheck=0).
    # Test the exact field, not a substring that would confuse the two settings.
    if not config.getboolean("nvidia-container-toolkit", "repo_gpgcheck", fallback=False):
        raise RuntimeError("NVIDIA RPM repository metadata signature verification is required")


def check_os(release_file=Path("/etc/os-release")):
    release = dict(line.split("=", 1) for line in release_file.read_text().splitlines() if "=" in line)
    identity = release.get("ID", "").strip('"').lower()
    version = release.get("VERSION_ID", "").strip('"')
    name = release.get("NAME", "").strip('"').lower()
    if (identity not in ("tencentos", "tencent", "tlinux") and "tencentos" not in name) or version.split(".")[0] != "4":
        raise RuntimeError("This installer targets TencentOS Server 4; it never replaces the OS")
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("x86_64 host required")


def check_gpu():
    if not shutil.which("nvidia-smi"):
        raise RuntimeError("NVIDIA driver missing; install TencentOS 580 driver or use --install-driver")
    report = run("nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                 "--format=csv,noheader", capture_output=True, text=True).stdout
    print(report, flush=True)
    gpu = [v.strip() for v in report.splitlines()[0].split(",")]
    if gpu[0] not in ("L20", "NVIDIA L20") or int(gpu[2].split()[0]) < 45000:
        raise RuntimeError("This deployment is sized for the full L20 48 GB")
    if int(gpu[1].split(".")[0]) < 580:
        raise RuntimeError("Driver branch 580 or newer required; GPU rendering is verified separately")


def install_driver():
    if shutil.which("nvidia-smi"):
        check_gpu()  # Existing drivers are not silently upgraded or replaced.
        return
    run("dnf", "install", "-y", "epol-release")
    run("dnf", "install", "-y", "gcc", "make", "dkms", "kernel-devel-" + os.uname().release)
    run("dnf", "install", "-y", "kmod-nvidia-580-dkms", "nvidia-580", "nvidia-driver-580")
    try:
        run("modprobe", "nvidia")
        check_gpu()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Driver installed but not ready. Inspect DKMS/nvidia-smi; reboot manually if needed, "
                           "then rerun this command. No automatic reboot.") from error


def prepare():
    run("dnf", "install", "-y", "ca-certificates", "curl")
    if not shutil.which("docker"):
        # TencentOS 4 is EL9 compatible, but $releasever is 4. Pin ONLY this
        # repository to EL9; never override the distribution's global releasever.
        repo = Path("/etc/yum.repos.d/hetao-docker-ce.repo")
        repo.write_text("[hetao-docker-ce]\nname=Docker CE EL9 for Hetao\n"
                        "baseurl=https://mirrors.cloud.tencent.com/docker-ce/linux/centos/9/$basearch/stable\n"
                        "enabled=1\ngpgcheck=1\n"
                        "gpgkey=https://mirrors.cloud.tencent.com/docker-ce/linux/centos/gpg\n")
        run("dnf", "install", "-y", "docker-ce", "docker-ce-cli", "containerd.io",
            "docker-buildx-plugin", "docker-compose-plugin")
    # Do not silently replace an existing Docker from another package source.
    run("docker", "compose", "version")
    run("docker", "buildx", "version")
    changed = storage.configure_docker()
    if not shutil.which("nvidia-ctk"):
        url = "https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo"
        with urlopen(url, timeout=60) as response:
            content = response.read().decode()
        validate_toolkit_repo(content)
        Path("/etc/yum.repos.d/nvidia-container-toolkit.repo").write_text(content)
        run("dnf", "install", "-y", "nvidia-container-toolkit")
    config = json.loads(Path("/etc/docker/daemon.json").read_text())
    if "nvidia" not in config.get("runtimes", {}):
        active = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True)
        if active.returncode == 0 and active.stdout.strip():
            raise RuntimeError("Docker has active containers; configure its NVIDIA runtime in a maintenance window")
        run("nvidia-ctk", "runtime", "configure", "--runtime=docker")
        changed = True
    # Bind the mount dependency to Docker too; /data must not fall back onto /.
    dropin = Path("/etc/systemd/system/docker.service.d/hetao-storage.conf")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    unit = "[Unit]\nRequiresMountsFor=/data/docker\nConditionPathIsMountPoint=/data\n"
    if not dropin.exists() or dropin.read_text() != unit:
        dropin.write_text(unit)
        run("systemctl", "daemon-reload")
    run("systemctl", "enable", "docker")
    run("systemctl", "restart" if changed else "start", "docker")
    storage.verify_docker()
