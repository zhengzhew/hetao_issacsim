"""Scene/robot catalogs: built-in JSON + user uploads, merged by id."""
from __future__ import annotations

from .app_context import ARGS, CATALOG_DIR, Path, UPLOAD_DIR, get_assets_root_path, json



def read_catalog(filename: str, key: str) -> list[dict]:
    payload = json.loads((CATALOG_DIR / filename).read_text(encoding="utf-8-sig"))
    items = payload.get(key)
    if not isinstance(items, list):
        raise ValueError(f"{filename} missing list {key}")
    return items


# User-added entries live beside the uploads rather than in configs/, because
# the web server and this process see different copies of configs/ (one in WSL,
# one on Windows) but a single shared uploads directory.
USER_CATALOG = UPLOAD_DIR / "catalog.json"


def read_user_catalog() -> dict:
    if not USER_CATALOG.is_file():
        return {"scenes": [], "robots": []}
    try:
        payload = json.loads(USER_CATALOG.read_text(encoding="utf-8-sig"))
        return {
            "scenes": [s for s in payload.get("scenes") or [] if isinstance(s, dict) and s.get("id")],
            "robots": [r for r in payload.get("robots") or [] if isinstance(r, dict) and r.get("id")],
        }
    except Exception as exc:
        print(f"[stage2] user catalog unreadable: {exc}", flush=True)
        return {"scenes": [], "robots": []}


SCENES: list[dict] = []
ROBOTS: list[dict] = []
SCENE_BY_ID: dict[str, dict] = {}
ROBOT_BY_ID: dict[str, dict] = {}


def reload_catalog() -> dict:
    """Re-read the built-in catalogs plus anything the user has uploaded."""
    global SCENES, ROBOTS, SCENE_BY_ID, ROBOT_BY_ID
    base_scenes = read_catalog("scenes.json", "scenes")
    base_robots = read_catalog("robots.json", "robots")
    user = read_user_catalog()
    # A user entry with the same id wins, so a built-in can be corrected in place.
    scenes = {item["id"]: {**item, "source": "builtin"} for item in base_scenes}
    robots = {item["id"]: {**item, "source": "builtin"} for item in base_robots}
    for item in user["scenes"]:
        scenes[item["id"]] = {**item, "source": "uploaded"}
    for item in user["robots"]:
        robots[item["id"]] = {**item, "source": "uploaded"}
    SCENES, ROBOTS = list(scenes.values()), list(robots.values())
    SCENE_BY_ID, ROBOT_BY_ID = scenes, robots
    return {"scenes": len(SCENES), "robots": len(ROBOTS),
            "uploaded": {"scenes": len(user["scenes"]), "robots": len(user["robots"])}}


reload_catalog()

ASSET_ROOT = ARGS.asset_root.strip() or (get_assets_root_path() or "")
if not ASSET_ROOT:
    raise RuntimeError("Could not resolve Isaac Sim asset root. Set ISAAC_ASSET_ROOT if assets are not discoverable.")


def asset_url(path_or_url: str) -> str:
    value = str(path_or_url or "").strip()
    # An uploaded asset is addressed as upload://<name>; the name is resolved
    # inside UPLOAD_DIR and may not escape it.
    if value.startswith("upload://"):
        # Deferred: uploads.py imports asset_url from here, so importing
        # resolve_upload at module load time would be circular.
        from .uploads import resolve_upload
        # Forward slashes: the USD resolver handles them consistently on both
        # platforms, backslashes only sometimes.
        return resolve_upload(value[len("upload://"):]).as_posix()
    if value.startswith(("omniverse://", "http://", "https://", "file://")):
        return value
    p = Path(value)
    if p.is_absolute() and p.exists():
        return str(p)
    if value.startswith("/Isaac/"):
        return ASSET_ROOT.rstrip("/") + value
    if value.startswith("Isaac/"):
        return ASSET_ROOT.rstrip("/") + "/" + value
    return value

