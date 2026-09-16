"""Uploaded USD asset validation and inspection."""
from __future__ import annotations

from .app_context import Path, UPLOAD_DIR, Usd, math
from .catalog import asset_url

# --- uploaded assets -------------------------------------------------------


# Windows reserves these as device names whether or not there is an extension.
WINDOWS_DEVICE_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def resolve_upload(name: str) -> Path:
    """Map an upload:// name onto a real file, refusing anything outside UPLOAD_DIR."""
    raw = str(name or "").strip()
    if "\\" in raw:
        raise ValueError(f"upload name may not contain backslashes: {name}")
    cleaned = raw.lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"bad upload name: {name}")
    for part in cleaned.split("/"):
        if not part or part == "." or part.rstrip(". ") != part:
            raise ValueError(f"bad path segment in upload name: {name}")
        if part.split(".")[0].lower() in WINDOWS_DEVICE_NAMES:
            raise ValueError(f"reserved Windows name in upload: {part}")
    target = (UPLOAD_DIR / cleaned).resolve()
    root = UPLOAD_DIR.resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"upload name escapes the upload directory: {name}")
    if not target.is_file():
        raise FileNotFoundError(f"uploaded asset not found: {cleaned}")
    return target


JOINT_TYPES = {
    "PhysicsRevoluteJoint": "revolute",
    "PhysicsPrismaticJoint": "prismatic",
    "PhysicsSphericalJoint": "spherical",
    "PhysicsFixedJoint": "fixed",
    "PhysicsDistanceJoint": "distance",
    "PhysicsJoint": "generic",
}


def _json_safe(value):
    """Strip inf/nan anywhere in a payload; JSON.parse rejects both."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def inspect_asset(args: dict) -> dict:
    """Open a USD file on its own stage and report what could be driven.

    Uploading a robot is useless without this: nothing in the file tells us
    which joints are wheels and which are arm joints, and getting a name wrong
    is exactly the "Invalid DOF name" failure that is hard to diagnose later.
    Opening a separate stage keeps the live simulation untouched.
    """
    from pxr import Usd, UsdGeom, UsdPhysics

    requested = str(args.get("asset_path") or "")
    if not requested.startswith("upload://"):
        raise ValueError("only uploaded assets can be inspected")
    path = asset_url(requested)
    # An overwritten upload keeps the same identifier, so USD may hand back the
    # previous file's layer from its cache.
    try:
        from pxr import Sdf
        cached = Sdf.Layer.Find(path)
        if cached is not None:
            cached.Reload(force=True)
    except Exception:
        pass
    stage = Usd.Stage.Open(path)
    if stage is None:
        raise RuntimeError(f"USD could not be opened: {path}")

    joints: list[dict] = []
    articulation_roots: list[str] = []
    meshes = 0
    total = 0
    default_prim = stage.GetDefaultPrim()

    for prim in stage.Traverse():
        total += 1
        type_name = str(prim.GetTypeName())
        if type_name == "Mesh":
            meshes += 1
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            articulation_roots.append(str(prim.GetPath()))
        kind = JOINT_TYPES.get(type_name)
        if kind is None or kind in {"fixed", "distance"}:
            continue
        entry = {"name": prim.GetName(), "path": str(prim.GetPath()), "type": kind}
        if kind in {"revolute", "prismatic"}:
            joint = UsdPhysics.RevoluteJoint(prim) if kind == "revolute" else UsdPhysics.PrismaticJoint(prim)
            try:
                entry["axis"] = str(joint.GetAxisAttr().Get())
                lower = joint.GetLowerLimitAttr().Get()
                upper = joint.GetUpperLimitAttr().Get()
                # Unauthored limits come back as -inf/+inf, which json.dumps
                # writes as `Infinity` and JSON.parse then refuses. A wheel is
                # exactly that case, so this must be filtered, not passed on.
                if (lower is not None and upper is not None
                        and math.isfinite(lower) and math.isfinite(upper) and lower < upper):
                    # UsdPhysics angular limits are degrees; Isaac drives radians.
                    entry["limit_unit"] = "degrees" if kind == "revolute" else "metres"
                    entry["limits"] = [float(lower), float(upper)]
                    if kind == "revolute":
                        entry["limits_rad"] = [math.radians(lower), math.radians(upper)]
                else:
                    entry["limits"] = None
                    entry["unlimited"] = True
            except Exception:
                pass
        joints.append(entry)

    extent = None
    try:
        if default_prim:
            bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(default_prim)
            box = bounds.ComputeAlignedRange()
            if not box.IsEmpty():
                extent = {"min": list(box.GetMin()), "max": list(box.GetMax()), "size": list(box.GetSize())}
    except Exception:
        pass

    return _json_safe({
        "path": path,
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0),
        "default_prim": str(default_prim.GetPath()) if default_prim else None,
        "prim_count": total,
        "mesh_count": meshes,
        "articulation_roots": articulation_roots,
        "joints": joints,
        # A file with no drivable joint can still be a scene; the caller decides.
        "looks_like_robot": bool(joints and articulation_roots),
    })

