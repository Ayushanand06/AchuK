
import logging
from functools import lru_cache

from app.config import (
    HELMET_MODEL, SEATBELT_MODEL, TRIPLE_MODEL,
    YOLO_CONF_THRESHOLD, YOLO_IOU_THRESHOLD, VEHICLE_CLASS_IDS,
)
from app.settings import settings

log = logging.getLogger("inference")


@lru_cache(maxsize=None)
def _load_yolo(weights_path: str):
    """Load a YOLO model once and cache it by path."""
    from ultralytics import YOLO
    log.info("Loading YOLO weights: %s", weights_path)
    model = YOLO(weights_path)
    model.overrides["conf"] = YOLO_CONF_THRESHOLD
    model.overrides["iou"] = YOLO_IOU_THRESHOLD
    model.overrides["imgsz"] = settings.inference_imgsz
    try:
        import torch
        if torch.cuda.is_available():
            model.overrides["half"] = True
    except Exception:
        pass
    log.info("Loaded %s — classes: %s", weights_path, model.names)
    return model


def get_helmet_model():
    return _load_yolo(HELMET_MODEL)


def get_seatbelt_model():
    return _load_yolo(SEATBELT_MODEL)


def get_triple_model():
    return _load_yolo(TRIPLE_MODEL)


def get_vehicle_model():
    """General COCO detector used only to feed vehicle bboxes to rule engines."""
    return _load_yolo(settings.vehicle_model_path)


def detect_vehicle_bboxes(frame):
    """Return [(x1,y1,x2,y2), ...] for COCO vehicle classes above threshold."""
    model = get_vehicle_model()
    results = model(frame, verbose=False)[0]
    boxes = []
    for box in results.boxes:
        if int(box.cls[0]) in VEHICLE_CLASS_IDS and float(box.conf[0]) >= YOLO_CONF_THRESHOLD:
            boxes.append(tuple(map(int, box.xyxy[0])))
    return boxes


@lru_cache(maxsize=1)
def get_detector():
    """Cached MultiModelDetector (loads the 3 violation models)."""
    from app.domain.detector import MultiModelDetector
    return MultiModelDetector()


@lru_cache(maxsize=1)
def get_ocr():
    """Cached PlateOCR (loads the plate model + OCR reader)."""
    from app.domain.ocr import PlateOCR
    return PlateOCR()


def warmup() -> dict:
    """
    Eagerly load every model and report the class names each exposes.
    Returns a dict for the /api/health/models endpoint and startup logging.
    """
    info = {}
    for name, getter in (
        ("helmet", get_helmet_model),
        ("seatbelt", get_seatbelt_model),
        ("triple", get_triple_model),
        ("vehicle", get_vehicle_model),
    ):
        try:
            model = getter()
            info[name] = {"loaded": True, "classes": dict(model.names)}
        except Exception as exc:  # pragma: no cover - surfaced via API
            info[name] = {"loaded": False, "error": str(exc)}
    try:
        get_ocr()
        info["plate"] = {"loaded": True}
    except Exception as exc:  # pragma: no cover
        info["plate"] = {"loaded": False, "error": str(exc)}
    return info
