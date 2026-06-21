# detector.py — Multi-model YOLOv8 violation detector
#
# This project ships FOUR separate single-purpose models (helmet, seatbelt,
# triple-riding, plate) instead of one unified multi-class model. This detector
# runs the three *violation* models, resolves each model's own class labels
# against config.MODEL_VIOLATION_MAP, and emits canonical ViolationEvents.
# The plate model is owned by ocr.PlateOCR, not here.

import logging
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from app.config import (
    MODEL_VIOLATION_MAP, MOTORCYCLE_KEYWORDS, PERSON_KEYWORDS,
    YOLO_CONF_THRESHOLD,
)
from app.services.inference import (
    get_helmet_model, get_seatbelt_model, get_triple_model,
)

log = logging.getLogger("detector")


# ── Data structures (unchanged contract for downstream cvcs/challan) ────────────

@dataclass
class Detection:
    """Single object detected in a frame."""
    class_id:     int
    label:        str
    confidence:   float
    bbox:         Tuple[int, int, int, int]   # x1, y1, x2, y2
    is_violation: bool = False


@dataclass
class ViolationEvent:
    """A confirmed traffic violation with its associated detections."""
    violation_type: str
    confidence:     float
    bbox:           Tuple[int, int, int, int]
    vehicle_bbox:   Optional[Tuple[int, int, int, int]] = None
    rider_count:    int = 1
    related:        List[Detection] = field(default_factory=list)


# ── Multi-model detector ────────────────────────────────────────────────────────

class MultiModelDetector:
    """
    Runs the helmet, seatbelt and triple-riding models on a single image and
    returns canonical ViolationEvents plus an annotated copy of the frame.

    Usage:
        detector = MultiModelDetector()
        violations, annotated = detector.detect(frame, camera_meta)
    """

    def __init__(self):
        self.helmet   = get_helmet_model()
        self.seatbelt = get_seatbelt_model()
        self.triple   = get_triple_model()

        # Pre-resolve each model's class-id -> canonical violation label.
        self._helmet_map   = self._resolve_violation_labels(self.helmet,   "helmet")
        self._seatbelt_map = self._resolve_violation_labels(self.seatbelt, "seatbelt")
        self._triple_map   = self._resolve_violation_labels(self.triple,   "triple")

        log.info("Helmet violation classes:   %s", self._helmet_map)
        log.info("Seatbelt violation classes: %s", self._seatbelt_map)
        log.info("Triple violation classes:   %s", self._triple_map)

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        camera_meta: dict = None,
    ) -> Tuple[List[ViolationEvent], np.ndarray]:
        """Run all three violation models and merge their findings."""
        violations: List[ViolationEvent] = []

        violations += self._detect_simple(self.helmet,   self._helmet_map, frame)
        violations += self._detect_simple(self.seatbelt, self._seatbelt_map, frame)
        violations += self._detect_triple(frame)

        annotated = self._draw(frame.copy(), violations)
        return violations, annotated

    # ── Per-model detection ────────────────────────────────────────────────────

    def _detect_simple(self, model, label_map: dict, frame: np.ndarray) -> List[ViolationEvent]:
        """
        Helmet / seatbelt: any detection whose class maps to a violation label
        is emitted directly (the models are trained to fire on the violation).
        """
        if not label_map:
            return []
        results = model(frame, verbose=False)[0]
        events = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            vtype = label_map.get(cls_id)
            if vtype is None:
                continue
            conf = float(box.conf[0])
            if conf < YOLO_CONF_THRESHOLD:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            events.append(ViolationEvent(
                violation_type=vtype,
                confidence=conf,
                bbox=(x1, y1, x2, y2),
            ))
        return events

    def _detect_triple(self, frame: np.ndarray) -> List[ViolationEvent]:
        """
        Triple riding. Two strategies depending on what the model emits:
          (a) a direct 'triple_riding' class  → emit per detection.
          (b) person + motorcycle classes     → count riders per two-wheeler;
              3+ overlapping persons = triple riding.
        """
        results = self.triple(frame, verbose=False)[0]
        names = self.triple.names

        # Strategy (a): direct triple class
        if self._triple_map:
            events = []
            for box in results.boxes:
                cls_id = int(box.cls[0])
                vtype = self._triple_map.get(cls_id)
                if vtype is None:
                    continue
                conf = float(box.conf[0])
                if conf < YOLO_CONF_THRESHOLD:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                events.append(ViolationEvent(
                    violation_type=vtype,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    rider_count=3,
                ))
            if events:
                return events

        # Strategy (b): count persons per motorcycle
        motos, persons = [], []
        for box in results.boxes:
            name = str(names.get(int(box.cls[0]), "")).lower()
            conf = float(box.conf[0])
            if conf < YOLO_CONF_THRESHOLD:
                continue
            bbox = tuple(map(int, box.xyxy[0]))
            det = Detection(int(box.cls[0]), name, conf, bbox)
            if any(k in name for k in MOTORCYCLE_KEYWORDS):
                motos.append(det)
            elif any(k in name for k in PERSON_KEYWORDS):
                persons.append(det)

        events = []
        for moto in motos:
            riders = [p for p in persons if self._iou(p.bbox, moto.bbox) > 0.08]
            if len(riders) >= 3:
                conf = float(np.mean([r.confidence for r in riders]))
                events.append(ViolationEvent(
                    violation_type="Triple riding",
                    confidence=conf,
                    bbox=moto.bbox,
                    vehicle_bbox=moto.bbox,
                    rider_count=len(riders),
                    related=riders + [moto],
                ))
        return events

    # ── Label resolution ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_violation_labels(model, model_key: str) -> dict:
        """
        Build {class_id -> canonical violation label} for one model by matching
        its real class names against MODEL_VIOLATION_MAP[model_key] substrings.
        """
        substr_map = MODEL_VIOLATION_MAP.get(model_key, {})
        resolved = {}
        for cls_id, raw_name in model.names.items():
            name = str(raw_name).lower().strip()
            for substr, vtype in substr_map.items():
                if substr in name:
                    resolved[int(cls_id)] = vtype
                    break
        return resolved

    # ── Annotation ─────────────────────────────────────────────────────────────

    @staticmethod
    def _draw(frame: np.ndarray, violations: List[ViolationEvent]) -> np.ndarray:
        for v in violations:
            x1, y1, x2, y2 = v.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 220), 3)
            label = f"{v.violation_type} ({v.confidence:.2f})"
            cv2.rectangle(frame, (x1, max(0, y1 - 22)),
                          (x1 + len(label) * 9, y1), (0, 0, 220), -1)
            cv2.putText(frame, label, (x1 + 2, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return frame

    # ── Geometry ───────────────────────────────────────────────────────────────

    @staticmethod
    def _iou(a, b) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return inter / ua if ua > 0 else 0.0
