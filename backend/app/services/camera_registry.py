
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from app.settings import settings
from app.config import CAMERA_DEFAULTS

log = logging.getLogger("camera_registry")


def _load_registry() -> Dict[str, dict]:
    registry: Dict[str, dict] = {}
    cam_dir = Path(settings.cameras_dir)
    if not cam_dir.exists():
        log.warning("Camera registry dir not found: %s", cam_dir)
        return registry
    for path in cam_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Skipping bad camera file %s: %s", path, exc)
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            cam_id = entry.get("camera_id")
            if cam_id:
                registry[cam_id] = entry
    return registry


_REGISTRY: Dict[str, dict] = _load_registry()


def reload() -> Dict[str, dict]:
    """Re-read the registry from disk (used after adding cameras)."""
    global _REGISTRY
    _REGISTRY = _load_registry()
    return _REGISTRY


def all_cameras() -> Dict[str, dict]:
    return _REGISTRY


def get_camera(camera_id: Optional[str]) -> Optional[dict]:
    if not camera_id:
        return None
    return _REGISTRY.get(camera_id)


def camera_meta(camera_id: Optional[str]) -> dict:
    """
    Build the camera_meta dict expected by the detector / CVCS / challan layer.
    Falls back to CAMERA_DEFAULTS for unknown or missing camera ids.
    """
    cam = get_camera(camera_id) or {}
    return {
        "camera_id":     camera_id or "CAM-UNKNOWN",
        "location":      cam.get("location", CAMERA_DEFAULTS["location"]),
        "zone":          cam.get("zone", CAMERA_DEFAULTS["zone"]),
        "resolution":    cam.get("resolution", CAMERA_DEFAULTS["resolution"]),
        "fps":           cam.get("fps", CAMERA_DEFAULTS["fps"]),
        "historical_fp": cam.get("historical_fp", CAMERA_DEFAULTS["historical_fp"]),
    }



CALIBRATION_DEFAULTS = {
    "stop_line_y":      None,
    "signal_roi":       None,
    "lane_boundary_x":  None,
    "expected_left_dx": 1.0,
    "no_parking_zones": [],
    "fps":              None,
}


def _calibration_path(camera_id: str) -> Path:
    return Path(settings.calibration_dir) / f"{camera_id}.json"


def get_calibration(camera_id: Optional[str]) -> dict:
    """Return the saved calibration merged over defaults (always complete)."""
    merged = dict(CALIBRATION_DEFAULTS)
    if camera_id:
        path = _calibration_path(camera_id)
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                merged.update({k: v for k, v in saved.items() if k in merged})
            except Exception as exc:
                log.warning("Bad calibration for %s: %s", camera_id, exc)
    return merged


def save_calibration(camera_id: str, calibration: dict) -> dict:
    """Persist calibration for a camera and return the stored (merged) result."""
    merged = dict(CALIBRATION_DEFAULTS)
    merged.update({k: v for k, v in calibration.items() if k in merged})
    path = _calibration_path(camera_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
