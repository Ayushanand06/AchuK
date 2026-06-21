# video_pipeline.py — frame-by-frame pipeline for time-dependent violations.
#
# Drives the existing rule engines (red-light, stop-line, wrong-side, illegal
# parking) plus the 4-model visual detector over a video clip, deduplicates
# repeated detections of the same ongoing violation, issues challans, and writes
# an annotated output video.

import logging
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from app.config import DEDUP_COOLDOWN_SEC
from app.domain.preprocessing import ImagePreprocessor
from app.domain.rule_engine import (
    StopLineDetector, RedLightDetector, WrongSideDetector,
    IllegalParkingDetector, RuleViolation,
)
from app.domain.cvcs import CVCSEngine, CVCSResult
from app.domain.challan import ChallanGenerator
from app.domain.ocr import PlateResult
from app.services.inference import get_detector, get_ocr, detect_vehicle_bboxes
from app.services import camera_registry

log = logging.getLogger("video_pipeline")


# ── Duplicate suppression ───────────────────────────────────────────────────────

class ViolationThrottle:
    """
    Suppresses repeat challans for the same ongoing violation. A violation is
    keyed by (type, coarse location cell); once issued, the same key is muted for
    `cooldown_sec` of *video* time.
    """

    def __init__(self, cooldown_sec: float, cell_px: int = 120):
        self.cooldown = cooldown_sec
        self.cell = cell_px
        self._last: dict = {}
        self.suppressed = 0

    def _key(self, vtype: str, bbox) -> tuple:
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        return (vtype, cx // self.cell, cy // self.cell)

    def allow(self, vtype: str, bbox, video_time_sec: float) -> bool:
        key = self._key(vtype, bbox)
        last = self._last.get(key)
        if last is not None and (video_time_sec - last) < self.cooldown:
            self.suppressed += 1
            return False
        self._last[key] = video_time_sec
        return True


# ── Pipeline ────────────────────────────────────────────────────────────────────

class VideoPipeline:
    """Process one video for a given (calibrated) camera."""

    def __init__(self, camera_id: Optional[str], progress_cb: Optional[Callable] = None):
        self.camera_id = camera_id
        self.meta = camera_registry.camera_meta(camera_id)
        self.calib = camera_registry.get_calibration(camera_id)
        self.progress_cb = progress_cb

        # Shared heavy objects (cached singletons).
        self.preprocessor = ImagePreprocessor()
        self.detector = get_detector()
        self.ocr = get_ocr()
        self.cvcs = CVCSEngine()
        self.challan_gen = ChallanGenerator()

        # Rule engines configured from calibration (None ⇒ inactive).
        c = self.calib
        self.stop_line = StopLineDetector(stop_line_y=c["stop_line_y"])
        self.red_light = RedLightDetector()
        if c["signal_roi"]:
            self.red_light.set_signal_roi(*c["signal_roi"])
        if c["stop_line_y"] is not None:
            self.red_light.set_stop_line(c["stop_line_y"])
        self.wrong_side = WrongSideDetector(
            lane_boundary_x=c["lane_boundary_x"],
            expected_left_dx=c["expected_left_dx"],
        )
        self.parking = IllegalParkingDetector(
            no_parking_zones=[np.array(z, dtype=np.int32) for z in (c["no_parking_zones"] or [])],
            fps=c["fps"] or self.meta["fps"],
        )

        self.throttle = ViolationThrottle(DEDUP_COOLDOWN_SEC)

        # Streaming state (used by step() for live feeds + the file loop).
        self._prev_frame = None
        self._prev_bboxes: List[Tuple] = []

        # Whether any rule engine is active — if not, we skip the COCO vehicle
        # model entirely (a big CPU win on uncalibrated cameras).
        ar = self.active_rules()
        self._rules_on = any(ar[k] for k in
                             ("stop_line", "red_light", "wrong_side", "illegal_parking"))

    # ── Which rules are active (surfaced in the job result) ──────────────────────

    def active_rules(self) -> dict:
        c = self.calib
        return {
            "stop_line":       c["stop_line_y"] is not None,
            "red_light":       bool(c["signal_roi"]) and c["stop_line_y"] is not None,
            "wrong_side":      c["lane_boundary_x"] is not None,
            "illegal_parking": bool(c["no_parking_zones"]),
            "helmet_seatbelt_triple": True,  # always on
        }

    # ── Single-frame step (shared by the file loop and live feeds) ───────────────

    def step(self, raw_frame, clock: float):
        """
        Process one raw frame. Returns (annotated_frame, issued_records, info).
        `clock` is the time (seconds) used for duplicate-suppression cooldown —
        video time for files, wall-clock for live feeds.
        """
        frame = self.preprocessor.process(raw_frame, is_video=True)
        lighting = self.preprocessor.lighting_score(frame)
        motion = (self.preprocessor.motion_magnitude(self._prev_frame, frame)
                  if self._prev_frame is not None else 0.0)
        h, w = frame.shape[:2]

        # Vehicle detection + rule engines only run when the camera is calibrated.
        if self._rules_on:
            vehicle_bboxes = detect_vehicle_bboxes(frame)
            signal_state, rl = self.red_light.check(frame, vehicle_bboxes, self._prev_bboxes)
            sl = self.stop_line.check(vehicle_bboxes, signal_state)
            ws = self.wrong_side.update_and_check(vehicle_bboxes)
            pk = self.parking.update_and_check(vehicle_bboxes)
            rule_violations: List[RuleViolation] = rl + sl + ws + pk
        else:
            vehicle_bboxes = []
            signal_state, rule_violations = "unknown", []

        visual, annotated = self.detector.detect(frame, self.meta)
        annotated = self._draw_rule_violations(annotated, rule_violations)
        annotated = self.stop_line.draw_line(annotated)
        annotated = self.parking.draw_zones(annotated)
        annotated = self._draw_signal_state(annotated, signal_state)

        merged = self._merge(visual, rule_violations)
        issued = []
        for v in merged:
            if not self.throttle.allow(v["violation_type"], v["bbox"], clock):
                continue
            plate = self._find_best_plate(frame, v["bbox"])
            plate_text = plate.cleaned_text if plate else "UNREAD"
            plate_conf = plate.ocr_conf if plate else 0.0
            cvcs: CVCSResult = self.cvcs.score(
                model_conf=v["confidence"], frame_width=w, frame_height=h,
                lighting_score=lighting, motion_magnitude=motion,
                camera_fp_rate=self.meta["historical_fp"], violation_type=v["violation_type"],
            )
            if cvcs.decision not in ("auto_challan", "review"):
                continue
            record = self.challan_gen.create(
                annotated_frame=annotated, plate_crop=plate.crop if plate else None,
                violation_type=v["violation_type"], plate_text=plate_text, plate_conf=plate_conf,
                cvcs_score=cvcs.final_score, cvcs_decision=cvcs.decision,
                camera_meta=self.meta, officer_id=None,
                extra_metadata={
                    "source": "video", "signal_state": signal_state,
                    "lighting": round(lighting, 4), "motion": round(motion, 4),
                    "explanation": cvcs.explanation,
                    "cvcs_factors": {
                        "model_conf": cvcs.model_conf, "resolution": cvcs.resolution_score,
                        "lighting": cvcs.lighting_score, "speed": cvcs.speed_score,
                        "camera_trust": cvcs.camera_score,
                    },
                },
            )
            issued.append(record)

        self._prev_frame = frame
        self._prev_bboxes = vehicle_bboxes
        return annotated, issued, {"signal_state": signal_state, "detections": len(merged)}

    # ── File loop (used by the background-job upload path) ────────────────────────

    def process(
        self,
        video_path: str,
        out_path: str,
        skip_frames: int = 2,
        max_frames: Optional[int] = None,
    ) -> dict:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        src_fps = cap.get(cv2.CAP_PROP_FPS) or (self.calib["fps"] or self.meta["fps"])
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        out_fps = max(1.0, src_fps / (skip_frames + 1))

        writer = None
        frame_count = 0
        processed = 0
        challans = []
        by_type: dict = {}

        try:
            while True:
                ret, raw = cap.read()
                if not ret:
                    break
                frame_count += 1
                if max_frames and processed >= max_frames:
                    break
                if skip_frames and (frame_count % (skip_frames + 1) != 0):
                    continue

                annotated, issued, _ = self.step(raw, frame_count / src_fps)
                for record in issued:
                    challans.append(record.challan_id)
                    by_type[record.violation_type] = by_type.get(record.violation_type, 0) + 1

                if writer is None:
                    h, w = annotated.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(out_path, fourcc, out_fps, (w, h))
                writer.write(annotated)

                processed += 1
                if self.progress_cb:
                    self.progress_cb(frame_count, total)
        finally:
            cap.release()
            if writer:
                writer.release()

        log.info("Video done: %d frames processed, %d challans, %d duplicates suppressed",
                 processed, len(challans), self.throttle.suppressed)

        return {
            "frames_total": total,
            "frames_processed": processed,
            "challan_count": len(challans),
            "challan_ids": challans,
            "by_type": by_type,
            "duplicates_suppressed": self.throttle.suppressed,
            "active_rules": self.active_rules(),
        }

    # ── Helpers (ported from the legacy pipeline) ────────────────────────────────

    @staticmethod
    def _merge(visual, rule_violations) -> List[dict]:
        out = []
        for v in visual:
            out.append({"violation_type": v.violation_type,
                        "confidence": v.confidence, "bbox": v.bbox})
        for v in rule_violations:
            out.append({"violation_type": v.violation_type,
                        "confidence": v.confidence, "bbox": v.bbox})
        return out

    @staticmethod
    def _draw_rule_violations(frame: np.ndarray, violations: List[RuleViolation]) -> np.ndarray:
        for v in violations:
            x1, y1, x2, y2 = v.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
            label = f"{v.violation_type} ({v.confidence:.2f})"
            cv2.rectangle(frame, (x1, max(0, y1 - 20)),
                          (x1 + len(label) * 8, y1), (0, 140, 255), -1)
            cv2.putText(frame, label, (x1 + 2, max(10, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        return frame

    @staticmethod
    def _draw_signal_state(frame: np.ndarray, state: str) -> np.ndarray:
        colours = {"red": (0, 0, 220), "green": (0, 200, 50),
                   "amber": (0, 165, 255), "unknown": (150, 150, 150)}
        colour = colours.get(state, (150, 150, 150))
        h, w = frame.shape[:2]
        cx, cy = w - 40, 40
        cv2.circle(frame, (cx, cy), 18, colour, -1)
        cv2.circle(frame, (cx, cy), 18, (255, 255, 255), 2)
        cv2.putText(frame, state.upper()[:3], (cx - 14, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        return frame

    def _find_best_plate(self, frame: np.ndarray, violation_bbox) -> Optional[PlateResult]:
        x1, y1, x2, y2 = violation_bbox
        h, w = frame.shape[:2]
        expand = 0.5
        sx1 = max(0, int(x1 - (x2 - x1) * expand))
        sy1 = max(0, int(y1 - (y2 - y1) * expand))
        sx2 = min(w, int(x2 + (x2 - x1) * expand))
        sy2 = min(h, int(y2 + (y2 - y1) * expand))
        region = frame[sy1:sy2, sx1:sx2]
        if region.size == 0:
            return None
        plates = self.ocr.find_plates(region)
        if not plates:
            return None
        results = []
        best_box, best_area = None, 0
        for pb in plates:
            pb_full = (pb[0] + sx1, pb[1] + sy1, pb[2] + sx1, pb[3] + sy1)
            area = (pb_full[2] - pb_full[0]) * (pb_full[3] - pb_full[1])
            if area > best_area:
                best_area, best_box = area, pb_full
            res = self.ocr.extract(frame, pb_full)
            if res:
                results.append(res)
        if results:
            valid = [r for r in results if r.is_valid]
            pool = valid if valid else results
            return max(pool, key=lambda r: r.ocr_conf)

        # OCR unreadable — still capture a plate snapshot for human review.
        crop = self.ocr.crop_plate(frame, best_box) if best_box else None
        if crop is None:
            return None
        return PlateResult(raw_text="", cleaned_text="UNREAD", is_valid=False,
                           ocr_conf=0.0, bbox=best_box, crop=crop)
