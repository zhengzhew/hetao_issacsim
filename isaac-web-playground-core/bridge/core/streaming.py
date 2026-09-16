"""MJPEG-compatibility frame capture and camera framing."""
from __future__ import annotations

from .app_context import ARGS, Usd, base64, kit, math, np, omni
from . import session
from .activity import note_activity

# --- MJPEG compatibility capture ------------------------------------------
#
# NVIDIA WebRTC needs UDP 47998 end to end. Behind a corporate VPN that NATs
# the client (GlobalProtect here) the UDP media never arrives, so the stream
# hangs at "Connecting" even though TCP signalling on 49100 is fine. This path
# renders the same viewport to JPEG frames and hands them back over the TCP
# bridge that already works, at the cost of frame rate and image quality.

_CAPTURE = {"render_product": None, "annotator": None, "size": None, "encoder": None, "error": None}


def _capture_available() -> bool:
    """True once we know replicator is importable; probed at most once."""
    if _CAPTURE["error"] is not None:
        return False
    if _CAPTURE["annotator"] is not None:
        return True
    try:
        import omni.replicator.core  # noqa: F401
        return True
    except Exception as exc:
        _CAPTURE["error"] = f"{type(exc).__name__}: {exc}"
        return False


CAPTURE_CAMERA_FALLBACK = "/World/PlaygroundCamera"


def _capture_camera_path() -> str:
    """The viewport camera if Kit made one, otherwise our own."""
    try:
        stage = omni.usd.get_context().get_stage()
        if stage is not None and stage.GetPrimAtPath("/OmniverseKit_Persp").IsValid():
            return "/OmniverseKit_Persp"
        from pxr import UsdGeom
        if stage is not None:
            if not stage.GetPrimAtPath(CAPTURE_CAMERA_FALLBACK).IsValid():
                UsdGeom.Camera.Define(stage, CAPTURE_CAMERA_FALLBACK)
                print(f"[stage2] no viewport camera; created {CAPTURE_CAMERA_FALLBACK}", flush=True)
            return CAPTURE_CAMERA_FALLBACK
    except Exception as exc:
        print(f"[stage2] camera lookup failed: {exc}", flush=True)
    return "/OmniverseKit_Persp"


def _release_capture() -> None:
    annotator = _CAPTURE.get("annotator")
    if annotator is not None:
        try:
            annotator.detach()
        except Exception:
            pass
    product = _CAPTURE.get("render_product")
    if product is not None:
        try:
            product.destroy()
        except Exception:
            pass
    _CAPTURE.update({"render_product": None, "annotator": None, "size": None})


def _ensure_capture(width: int, height: int) -> None:
    """Attach an rgb annotator to the perspective viewport, reusing it across frames."""
    if _CAPTURE["annotator"] is not None and _CAPTURE["size"] == (width, height):
        return
    import omni.replicator.core as rep

    _release_capture()
    camera_path = _capture_camera_path()
    product = rep.create.render_product(camera_path, (width, height))
    try:
        annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        annotator.attach([product])
    except Exception:
        try:
            product.destroy()
        except Exception:
            pass
        raise
    _CAPTURE.update({"render_product": product, "annotator": annotator, "size": (width, height)})
    # The annotator needs a few app updates before it produces a full frame.
    for _ in range(4):
        kit.update()


def _encode_png(rgb: "np.ndarray") -> tuple[str, bytes]:
    """Dependency-free fallback if Pillow is unavailable inside Kit's Python."""
    import struct
    import zlib

    height, width, _ = rgb.shape
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        rows.extend(rgb[y].tobytes())

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 1))
    png += chunk(b"IEND", b"")
    return "image/png", png


def _encode_frame(rgb: "np.ndarray", quality: int) -> tuple[str, bytes]:
    if _CAPTURE["encoder"] != "png":
        try:
            import io

            from PIL import Image

            buffer = io.BytesIO()
            Image.fromarray(rgb).save(buffer, format="JPEG", quality=quality, optimize=False)
            _CAPTURE["encoder"] = "jpeg"
            return "image/jpeg", buffer.getvalue()
        except Exception as exc:
            _CAPTURE["encoder"] = "png"
            print(f"[stage2] Pillow unavailable, falling back to PNG frames: {exc}", flush=True)
    return _encode_png(rgb)


def capture_frame(args: dict) -> dict:
    note_activity("capture")
    # Quantised so that a client tracking its window size cannot force a
    # render-product rebuild on every frame.
    width = max(160, min(1920, int(args.get("width") or ARGS.capture_width))) // 16 * 16
    height = max(120, min(1080, int(args.get("height") or ARGS.capture_height))) // 16 * 16
    quality = max(20, min(95, int(args.get("quality") or 60)))
    _ensure_capture(width, height)
    frame = None
    problem = None
    # The annotator is refreshed by the main loop, so the first read usually
    # already has a frame. Paying for an extra kit.update() per capture is a
    # whole render pass on the thread teleop shares.
    for attempt in range(4):
        if attempt:
            kit.update()
        data = _CAPTURE["annotator"].get_data()
        if isinstance(data, dict):
            data = data.get("data", data)
        # Warp / torch arrays are GPU resident; np.asarray gives a 0-d object.
        for converter in ("numpy", "cpu"):
            if hasattr(data, converter):
                try:
                    data = getattr(data, converter)()
                    break
                except Exception:
                    pass
        candidate = np.asarray(data)
        if candidate.size and candidate.ndim == 3 and candidate.shape[2] >= 3:
            frame = candidate
            break
        problem = f"shape={getattr(candidate, 'shape', None)} type={type(data).__name__}"
    if frame is None:
        raise RuntimeError(f"viewport annotator returned an unusable frame after 4 updates: {problem}")
    rgb = np.ascontiguousarray(frame[:, :, :3].astype(np.uint8))
    mime, payload = _encode_frame(rgb, quality)
    return {
        "mime": mime,
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "encoder": _CAPTURE["encoder"],
        "data": base64.b64encode(payload).decode("ascii"),
    }


# --- camera, for the compatibility path -----------------------------------
#
# WebRTC forwards mouse and keyboard straight into the Kit viewport. MJPEG
# frames are one-way, so the camera has to be driven explicitly instead.

CAMERA = {"eye": [4.0, -5.0, 3.0], "target": [0.0, 0.0, 0.4]}


def apply_camera(eye: list[float], target: list[float]) -> dict:
    note_activity("command")
    for name, value in (("eye", eye), ("target", target)):
        ok = len(value) == 3 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e4 for v in value
        )
        if not ok:
            raise ValueError(f"camera {name} must be three finite numbers")
    if all(abs(a - b) < 1e-6 for a, b in zip(eye, target)):
        raise ValueError("camera eye and target must differ")
    try:
        from isaacsim.core.utils.viewports import set_camera_view
    except ImportError:
        from isaacsim.core.experimental.utils.viewports import set_camera_view
    set_camera_view(eye=list(eye), target=list(target), camera_prim_path="/OmniverseKit_Persp")
    CAMERA["eye"] = [float(v) for v in eye]
    CAMERA["target"] = [float(v) for v in target]
    return dict(CAMERA)


_VIEW_DIRECTION = (0.62, -0.62, 0.48)     # from the robot towards the camera
_ASPECT = 16.0 / 9.0


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _vertical_fov_degrees(aspect: float = _ASPECT) -> float:
    """The viewport's vertical field of view, measured rather than assumed.

    Kit's default perspective camera is 60 degrees horizontal, but a scene may
    author its own, and framing computed against the wrong number is either
    cropped or lost in a sea of floor.
    """
    try:
        from pxr import UsdGeom
        stage = omni.usd.get_context().get_stage()
        cam = UsdGeom.Camera(stage.GetPrimAtPath("/OmniverseKit_Persp"))
        focal = float(cam.GetFocalLengthAttr().Get())
        aperture = float(cam.GetHorizontalApertureAttr().Get())
        if focal > 0 and aperture > 0:
            half_h = math.atan(aperture / (2.0 * focal))
            return math.degrees(2.0 * math.atan(math.tan(half_h) / aspect))
    except Exception:
        pass
    return 36.0            # 60 degrees horizontal at 16:9


def frame_robot(prim_path: str, fallback: dict, margin: float = 1.15) -> dict | None:
    """Point the camera at the robot, sized to whatever it actually is.

    Scene cameras are authored for the scene, not for a 30 cm arm dropped into
    it. Without this the robot loads correctly and is invisible, which reads as
    a failure.
    """
    try:
        from pxr import Usd, UsdGeom
        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        box = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if box.IsEmpty():
            return None
        centre = [float(v) for v in box.GetMidpoint()]
        size = [float(v) for v in box.GetSize()]
        # Half the diagonal, not the longest side: an arm reaching diagonally
        # across the view is wider on screen than any single axis says, and
        # sizing to the longest side alone crops it.
        radius = 0.5 * math.sqrt(sum(v * v for v in size)) if size else 1.0
        if not math.isfinite(radius) or radius <= 0:
            return None
        # Distance from the camera's real field of view rather than a constant:
        # the vertical axis is the tighter one on a 16:9 stream, so fit to that.
        # Normalised, so `distance` below is the distance -- the original
        # direction vector was 1.19 units long and quietly pushed the camera
        # 19% further out than the number said.
        norm = math.sqrt(sum(v * v for v in _VIEW_DIRECTION))
        direction = tuple(v / norm for v in _VIEW_DIRECTION)
        # Fit the box as it actually projects, not its bounding sphere. A
        # sphere fit never crops from any angle, but on a shape like this arm
        # -- 44 cm long, 14 cm deep, 25 cm tall -- it spends well over half the
        # frame on empty floor.
        forward = tuple(-v for v in direction)
        right = _cross(forward, (0.0, 0.0, 1.0))
        length = math.sqrt(sum(v * v for v in right))
        right = (1.0, 0.0, 0.0) if length < 1e-6 else tuple(v / length for v in right)
        up = _cross(right, forward)
        half_v = math.radians(_vertical_fov_degrees()) / 2.0
        half_h = math.atan(math.tan(half_v) * _ASPECT)
        low, high = box.GetMin(), box.GetMax()
        span_right = span_up = 0.0
        for x in (low[0], high[0]):
            for y in (low[1], high[1]):
                for z in (low[2], high[2]):
                    offset = (x - centre[0], y - centre[1], z - centre[2])
                    span_right = max(span_right, abs(sum(offset[i] * right[i] for i in range(3))))
                    span_up = max(span_up, abs(sum(offset[i] * up[i] for i in range(3))))
        needed = max(span_up / math.tan(half_v), span_right / math.tan(half_h))
        distance = max(0.35, needed * float(margin))
        eye = [centre[i] + distance * direction[i] for i in range(3)]
        target = [centre[0], centre[1], centre[2] + radius * 0.12]
        # Report the spans, not the radius: since the switch to a projected fit
        # the radius no longer determines the distance, and logging it invites
        # exactly the wrong arithmetic when someone checks the number.
        print(f"[stage2] framing robot: size={[round(v, 3) for v in size]} "
              f"span=({span_right:.3f},{span_up:.3f}) vfov={math.degrees(half_v)*2:.1f}deg "
              f"margin={float(margin):.2f} distance={distance:.2f}m", flush=True)
        return apply_camera(eye, target)
    except Exception as exc:
        print(f"[stage2] could not frame the robot: {type(exc).__name__}: {exc}", flush=True)
        return None


def camera_defaults() -> dict:
    scene = session.CURRENT_SCENE or {}
    return {
        "eye": list(scene.get("camera_eye") or [4.0, -5.0, 3.0]),
        "target": list(scene.get("camera_target") or [0.0, 0.0, 0.4]),
    }

