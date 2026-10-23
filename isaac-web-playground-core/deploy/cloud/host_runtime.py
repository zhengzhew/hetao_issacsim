"""Boot the installed TencentOS host with cached images and an explicitly saved IP."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

import manage

DATA = Path("/srv/hetao-isaac")


def public_ip(value):
    # Address store browsers use to reach this host. Public IPv4 for the ACME
    # path, or a routed private/VPN IPv4 when the site has no inbound internet.
    address = ipaddress.ip_address(value.strip())
    if address.version != 4 or address.is_unspecified or address.is_multicast:
        raise ValueError("A reachable IPv4 address is required")
    return str(address)


def configured_identity(directory, machine_file=Path("/etc/machine-id")):
    # No cloud metadata dependency or outbound "what is my IP" lookup. An
    # outbound NAT IP would not prove the browser can reach this machine.
    address = public_ip(json.loads((directory / "host.json").read_text())["publicIp"])
    machine = machine_file.read_text().strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", machine):
        raise ValueError("Invalid /etc/machine-id")
    return {"instanceId": "host-" + hashlib.sha256(machine.encode()).hexdigest()[:32], "publicIp": address}


def write_private(path, value, container=False):
    """Atomic file update; only call while containers that mount it are stopped."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".new")
    temp.write_text(value, encoding="utf-8")
    temp.chmod(0o600)
    if container and sys.platform == "linux" and os.geteuid() == 0:
        os.chown(temp, 1234, 1234)
    temp.replace(path)


def save_json(path, value, container=False):
    write_private(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", container)


def update_identity(directory, identity):
    """Same-machine restarts preserve login. Clones cannot reuse old access tokens."""
    path = directory / "host-identity.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    cloned = old is not None and old["instanceId"] != identity["instanceId"]
    if cloned:
        key = secrets.token_urlsafe(32)
        write_private(directory / "worker-key", key + "\n", True)
        access_path = directory / "state/platform/access.json"
        if access_path.exists():
            access = json.loads(access_path.read_text(encoding="utf-8"))
            access.update(credentials={}, codes={}, workerKey=key)
            save_json(access_path, access, True)
    manage.configure_public(directory, identity["publicIp"])
    save_json(path, identity)
    return cloned


def initialize_teacher(directory, password):
    access_path = directory / "state/platform/access.json"
    if access_path.exists():
        return False  # Upgrades must not reset an existing teacher password.
    salt = secrets.token_hex(16)
    value = {"salt": salt, "passwordHash": hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32).hex(),
        "workerKey": secrets.token_urlsafe(32), "credentials": {}, "codes": {}, "audit": [], "arms": {}}
    save_json(access_path, value, True)
    write_private(directory / "state/platform/teacher-password.txt", password + "\n", True)
    return True


def status(directory, phase, **details):
    save_json(directory / "startup-status.json", {"phase": phase, "at": int(time.time()), **details})


def start(directory, timeout=900):
    status(directory, "starting")
    # Do not launch containers with an unvalidated or stale saved configuration.
    try:
        compose = manage.compose_command(directory)
        subprocess.run(compose + ["down", "--timeout", "60"], check=True)
        identity = configured_identity(directory)
        update_identity(directory, identity)
        subprocess.run(manage.compose_command(directory) +
                       ["up", "-d", "--no-build", "--pull", "never"], check=True)
        if manage.wait_ready(directory, timeout):
            raise RuntimeError("Scene not ready; inspect docker compose logs")
        status(directory, "scene-ready", url=f"https://{identity['publicIp']}/",
               browserVideoVerified=False, instanceId=identity["instanceId"])
    except Exception as error:
        status(directory, "failed", error=str(error))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--directory", type=Path, default=DATA)
    args = parser.parse_args()
    if args.action == "start":
        start(args.directory)
    elif args.action == "status":
        print((args.directory / "startup-status.json").read_text(encoding="utf-8"))
    elif args.action == "stop":
        subprocess.run(manage.compose_command(args.directory) + ["down", "--timeout", "60"], check=True)
        status(args.directory, "stopped")
        print("Containers stopped. VM billing continues; stop the VM in the cloud console.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
