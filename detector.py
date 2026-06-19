# detector.py — YOLOv8 multi-violation detector
# Runs a single inference pass and fans out to per-violation logic

import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from ultralytics import YOLO

from config import (
    MODEL_PATH, CLASS_NAMES, VIOLATION_CLASSES, VIOLATION_LABELS,
    YOLO_CONF_THRESHOLD, YOLO_IOU_THRESHOLD
)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class Detection:
    """Single object detected in a frame."""
    class_id:   int
    label:      str
    confidence: float
    bbox:       Tuple[int, int, int, int]   # x1, y1, x2, y2
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


# ── Main detector class ────────────────────────────────────────────────────────

class ViolationDetector:
    """
    Wraps YOLOv8 and applies per-violation post-processing logic.

    Single backbone inference pass → multiple violation checks:
      - No helmet   (class 7 detected near motorcycle + rider)
      - No seatbelt (class 9 detected in vehicle bounding box)
      - Triple riding (3+ persons on class 2 / motorcycle)
      - Red-light run (vehicle in intersection when class 13 active)
      - Wrong-side   (vehicle motion vector against lane direction)

    Usage:
        detector = ViolationDetector()
        violations, annotated_frame = detector.detect(frame, camera_meta)
    """

    def __init__(self):
        self.model = YOLO(MODEL_PATH)
        self.model.overrides["conf"] = YOLO_CONF_THRESHOLD
        self.model.overrides["iou"]  = YOLO_IOU_THRESHOLD

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        camera_meta: dict = None
    ) -> Tuple[List[ViolationEvent], np.ndarray]:
        """
        Run detection on a preprocessed frame.

        Returns:
            violations     — list of ViolationEvent objects
            annotated      — frame with bounding boxes drawn
        """
        results = self.model(frame, verbose=False)[0]
        detections = self._parse_results(results)

        violations = []
        violations += self._check_helmet(detections)
        violations += self._check_seatbelt(detections)
        violations += self._check_triple_riding(detections)
        violations += self._check_red_light(detections)
        violations += self._check_wrong_side(detections, camera_meta)

        annotated = self._draw_annotations(frame.copy(), detections, violations)
        return violations, annotated

    # ── Parse raw YOLO output ─────────────────────────────────────────────────

    def _parse_results(self, results) -> List[Detection]:
        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append(Detection(
                class_id     = cls_id,
                label        = CLASS_NAMES.get(cls_id, "unknown"),
                confidence   = conf,
                bbox         = (x1, y1, x2, y2),
                is_violation = cls_id in VIOLATION_CLASSES,
            ))
        return detections

    # ── Violation logic ───────────────────────────────────────────────────────

    def _check_helmet(self, detections: List[Detection]) -> List[ViolationEvent]:
        """
        No-helmet violation: class 7 (no_helmet) detected AND overlaps
        with a motorcycle (class 2) bounding box.
        """
        violations = []
        motos  = [d for d in detections if d.class_id == 2]
        no_hel = [d for d in detections if d.class_id == 7]

        for nh in no_hel:
            for moto in motos:
                if self._iou(nh.bbox, moto.bbox) > 0.10:
                    violations.append(ViolationEvent(
                        violation_type = VIOLATION_LABELS[7],
                        confidence     = nh.confidence,
                        bbox           = nh.bbox,
                        vehicle_bbox   = moto.bbox,
                        related        = [nh, moto],
                    ))
                    break
        return violations

    def _check_seatbelt(self, detections: List[Detection]) -> List[ViolationEvent]:
        """
        No-seatbelt: class 9 detected inside a car (class 3) bounding box.
        """
        violations = []
        cars   = [d for d in detections if d.class_id == 3]
        no_sb  = [d for d in detections if d.class_id == 9]

        for ns in no_sb:
            for car in cars:
                if self._box_inside(ns.bbox, car.bbox, threshold=0.5):
                    violations.append(ViolationEvent(
                        violation_type = VIOLATION_LABELS[9],
                        confidence     = ns.confidence,
                        bbox           = ns.bbox,
                        vehicle_bbox   = car.bbox,
                        related        = [ns, car],
                    ))
                    break
        return violations

    def _check_triple_riding(self, detections: List[Detection]) -> List[ViolationEvent]:
        """
        Triple riding: 3 or more persons (class 0) clustered on or
        heavily overlapping a motorcycle (class 2).
        """
        violations = []
        motos   = [d for d in detections if d.class_id == 2]
        persons = [d for d in detections if d.class_id == 0]

        for moto in motos:
            riders = [p for p in persons
                      if self._iou(p.bbox, moto.bbox) > 0.08]
            if len(riders) >= 3:
                conf = float(np.mean([r.confidence for r in riders]))
                violations.append(ViolationEvent(
                    violation_type = VIOLATION_LABELS[11],
                    confidence     = conf,
                    bbox           = moto.bbox,
                    vehicle_bbox   = moto.bbox,
                    rider_count    = len(riders),
                    related        = riders + [moto],
                ))
        return violations

    def _check_red_light(self, detections: List[Detection]) -> List[ViolationEvent]:
        """
        Red-light run: vehicle (car/moto/bus/truck) detected PAST the
        stop line when a red light (class 13) is active in the scene.
        """
        violations = []
        red_lights  = [d for d in detections if d.class_id == 13]
        stop_lines  = [d for d in detections if d.class_id == 12]
        vehicles    = [d for d in detections if d.class_id in {2, 3, 4, 5}]

        if not red_lights:
            return violations

        for veh in vehicles:
            for sl in stop_lines:
                # vehicle centroid is below (past) the stop-line centroid
                veh_cy = (veh.bbox[1] + veh.bbox[3]) // 2
                sl_cy  = (sl.bbox[1]  + sl.bbox[3])  // 2
                if veh_cy > sl_cy:
                    conf = float(np.mean([r.confidence for r in red_lights]))
                    violations.append(ViolationEvent(
                        violation_type = VIOLATION_LABELS[13],
                        confidence     = conf,
                        bbox           = veh.bbox,
                        vehicle_bbox   = veh.bbox,
                        related        = red_lights + [veh] + stop_lines,
                    ))
                    break
        return violations

    def _check_wrong_side(
        self,
        detections: List[Detection],
        camera_meta: Optional[dict]
    ) -> List[ViolationEvent]:
        """
        Wrong-side driving: vehicle detected in the lane half that is
        designated for opposite traffic. Requires camera_meta to know
        which image half corresponds to which lane direction.

        camera_meta keys used:
            "wrong_side_x_threshold" — x pixel boundary of lane split
            "wrong_side_direction"   — "left" | "right" (inbound lane)
        """
        if not camera_meta or "wrong_side_x_threshold" not in camera_meta:
            return []

        violations = []
        threshold   = camera_meta["wrong_side_x_threshold"]
        inbound_side = camera_meta.get("wrong_side_direction", "left")
        vehicles    = [d for d in detections if d.class_id in {2, 3, 4, 5}]

        for veh in vehicles:
            veh_cx = (veh.bbox[0] + veh.bbox[2]) // 2
            on_wrong = (
                (inbound_side == "left"  and veh_cx < threshold) or
                (inbound_side == "right" and veh_cx > threshold)
            )
            if on_wrong:
                violations.append(ViolationEvent(
                    violation_type = VIOLATION_LABELS[15],
                    confidence     = veh.confidence,
                    bbox           = veh.bbox,
                    vehicle_bbox   = veh.bbox,
                    related        = [veh],
                ))
        return violations

    # ── Annotation ────────────────────────────────────────────────────────────

    def _draw_annotations(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        violations: List[ViolationEvent],
    ) -> np.ndarray:
        """
        Draw green boxes for normal detections, red boxes + labels for
        violations. Confidence score shown on each box.
        """
        violation_bboxes = {v.bbox for v in violations}

        for d in detections:
            color = (0, 0, 220) if d.bbox in violation_bboxes else (0, 200, 0)
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{d.label} {d.confidence:.2f}"
            cv2.putText(frame, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        for v in violations:
            x1, y1, x2, y2 = v.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 220), 3)
            label = f"VIOLATION: {v.violation_type} ({v.confidence:.2f})"
            cv2.rectangle(frame, (x1, y1 - 22), (x1 + len(label)*9, y1),
                          (0, 0, 220), -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return frame

    # ── Geometry helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _iou(a, b) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        ua = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / ua if ua > 0 else 0.0

    @staticmethod
    def _box_inside(inner, outer, threshold=0.5) -> bool:
        """Returns True if ≥ threshold fraction of inner box overlaps outer."""
        ix1, iy1, ix2, iy2 = inner
        ox1, oy1, ox2, oy2 = outer
        inter_w = max(0, min(ix2, ox2) - max(ix1, ox1))
        inter_h = max(0, min(iy2, oy2) - max(iy1, oy1))
        inter   = inter_w * inter_h
        inner_a = max(1, (ix2 - ix1) * (iy2 - iy1))
        return (inter / inner_a) >= threshold