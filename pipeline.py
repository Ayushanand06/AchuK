# pipeline.py — Complete VisionEnforce end-to-end pipeline
#
# Combines:
#   preprocessing.py  → image enhancement
#   detector.py       → YOLOv8 visual violation detection (helmet, seatbelt, triple)
#   rule_engine.py    → logic-based detection (stop-line, red-light, wrong-side, parking)
#   ocr.py            → license plate recognition
#   cvcs.py           → contextual confidence scoring
#   challan.py        → evidence packet generation
#   analytics.py      → trend reporting

import cv2
import numpy as np
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from pathlib import Path

from preprocessing import ImagePreprocessor
from detector import ViolationDetector, ViolationEvent
from rule_engine import (
    StopLineDetector, RedLightDetector,
    WrongSideDetector, IllegalParkingDetector, RuleViolation,
)
from ocr import PlateOCR, PlateResult
from cvcs import CVCSEngine, CVCSResult
from challan import ChallanGenerator, ChallanRecord
from analytics import AnalyticsEngine
from config import CAMERA_DEFAULTS


# ── Per-camera calibration profile ────────────────────────────────────────────

@dataclass
class CameraProfile:
    """
    All camera-specific calibration values.
    Load from a JSON config file per camera_id in production.

    Example:
        profile = CameraProfile.from_json("configs/cameras/CAM-019.json")
    """
    camera_id:            str
    location:             str
    zone:                 str
    resolution:           str = "1080p"
    fps:                  float = 25.0
    historical_fp:        float = 0.05

    # Rule engine calibration
    stop_line_y:          Optional[int] = None    # pixel y of stop line
    signal_roi:           Optional[Tuple[int,int,int,int]] = None  # traffic light ROI
    lane_boundary_x:      Optional[int] = None    # pixel x of lane centre
    expected_left_dx:     float = 1.0             # +1 = left→right in left lane
    no_parking_zones:     List = field(default_factory=list)
    wrong_side_x_threshold: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "CameraProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, path: str) -> "CameraProfile":
        import json
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def to_camera_meta(self) -> dict:
        """Convert to the camera_meta dict expected by detector and CVCS."""
        return {
            "camera_id":              self.camera_id,
            "location":               self.location,
            "zone":                   self.zone,
            "resolution":             self.resolution,
            "fps":                    self.fps,
            "historical_fp":          self.historical_fp,
            "wrong_side_x_threshold": self.wrong_side_x_threshold,
            "wrong_side_direction":   "left" if self.expected_left_dx > 0 else "right",
        }


# ── Per-frame result ───────────────────────────────────────────────────────────

@dataclass
class FrameResult:
    """Complete output for one processed frame."""
    frame_id:        int
    timestamp:       float                     # unix timestamp
    annotated_frame: np.ndarray
    signal_state:    str
    violations:      List[dict]                # merged visual + rule violations
    challans:        List[ChallanRecord]       # issued challan records
    processing_ms:   float                    # inference time


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE CLASS
# ══════════════════════════════════════════════════════════════════════════════

class VisionEnforcePipeline:
    """
    Complete VisionEnforce processing pipeline.

    Architecture:
        Frame
          │
          ▼
        ImagePreprocessor          ← CLAHE, shadow removal, motion blur
          │
          ▼
        ViolationDetector          ← YOLOv8: helmet, seatbelt, triple riding
          │
          ├──► StopLineDetector    ← Rule: vehicle past calibrated line
          ├──► RedLightDetector    ← Rule: signal colour + moving vehicle
          ├──► WrongSideDetector   ← Rule: direction vector vs lane
          └──► IllegalParkingDetector  ← Rule: stationary in restricted zone
          │
          ▼
        PlateOCR                   ← Super-res + PaddleOCR
          │
          ▼
        CVCSEngine                 ← Contextual confidence scoring
          │
          ├── auto_challan ──► ChallanGenerator  ← evidence packet + hash
          ├── review       ──► review queue
          └── discard
          │
          ▼
        AnalyticsEngine            ← trends, PDI recommendations

    Usage (image):
        pipeline = VisionEnforcePipeline(profile)
        result = pipeline.process_frame(frame)

    Usage (video file):
        for result in pipeline.process_video("clip.mp4"):
            display(result.annotated_frame)

    Usage (live camera):
        for result in pipeline.process_stream(camera_index=0):
            display(result.annotated_frame)
    """

    def __init__(self, profile: CameraProfile):
        self.profile      = profile
        self.camera_meta  = profile.to_camera_meta()

        # ── Module initialisation ──────────────────────────────────────────
        self.preprocessor = ImagePreprocessor()
        self.detector     = ViolationDetector()
        self.ocr          = PlateOCR()
        self.cvcs         = CVCSEngine()
        self.challan_gen  = ChallanGenerator()
        self.analytics    = AnalyticsEngine()

        # ── Rule engines ───────────────────────────────────────────────────
        self.stop_line    = StopLineDetector(stop_line_y=profile.stop_line_y)
        self.red_light    = RedLightDetector()
        self.wrong_side   = WrongSideDetector(
            lane_boundary_x  = profile.lane_boundary_x,
            expected_left_dx = profile.expected_left_dx,
        )
        self.parking      = IllegalParkingDetector(
            no_parking_zones = [np.array(z, dtype=np.int32)
                                for z in profile.no_parking_zones],
            fps              = profile.fps,
        )

        if profile.signal_roi:
            self.red_light.set_signal_roi(*profile.signal_roi)
        if profile.stop_line_y:
            self.red_light.set_stop_line(profile.stop_line_y)

        # ── State ──────────────────────────────────────────────────────────
        self._frame_id    = 0
        self._prev_frame: Optional[np.ndarray] = None
        self._prev_bboxes: List[Tuple] = []

    # ══════════════════════════════════════════════════════════════════════════
    #  CORE: process a single frame
    # ══════════════════════════════════════════════════════════════════════════

    def process_frame(
        self,
        raw_frame: np.ndarray,
        is_video:  bool = False,
    ) -> FrameResult:
        """
        Full pipeline for one frame. Returns FrameResult with all violations,
        annotated image, and issued challans.
        """
        t0 = time.time()
        self._frame_id += 1

        # ── Step 1: Preprocess ─────────────────────────────────────────────
        frame = self.preprocessor.process(raw_frame, is_video=is_video)

        # Compute lighting score for CVCS
        lighting = self.preprocessor.lighting_score(frame)

        # Compute motion magnitude (for speed-based CVCS weight)
        motion = 0.0
        if self._prev_frame is not None and is_video:
            motion = self.preprocessor.motion_magnitude(self._prev_frame, frame)

        # ── Step 2: YOLOv8 visual detection ───────────────────────────────
        yolo_violations, annotated = self.detector.detect(frame, self.camera_meta)

        # ── Step 3: Extract vehicle bboxes for rule engines ────────────────
        vehicle_classes = {2, 3, 4, 5}    # motorcycle, car, bus, truck
        vehicle_bboxes  = []
        raw_results     = self.detector.model(frame, verbose=False)[0]
        for box in raw_results.boxes:
            if int(box.cls[0]) in vehicle_classes:
                vehicle_bboxes.append(tuple(map(int, box.xyxy[0])))

        # ── Step 4: Rule-based detection ──────────────────────────────────
        signal_state, rl_violations = self.red_light.check(
            frame, vehicle_bboxes, self._prev_bboxes
        )
        sl_violations  = self.stop_line.check(vehicle_bboxes, signal_state)
        ws_violations  = self.wrong_side.update_and_check(vehicle_bboxes)
        pk_violations  = self.parking.update_and_check(vehicle_bboxes)

        rule_violations: List[RuleViolation] = (
            rl_violations + sl_violations + ws_violations + pk_violations
        )

        # ── Step 5: Annotate rule violations on frame ──────────────────────
        annotated = self._draw_rule_violations(annotated, rule_violations)
        annotated = self.stop_line.draw_line(annotated)
        annotated = self.parking.draw_zones(annotated)
        annotated = self._draw_signal_state(annotated, signal_state)

        # ── Step 6: Collect all violations ────────────────────────────────
        all_violations = self._merge_violations(yolo_violations, rule_violations)

        # ── Step 7: OCR + CVCS + challan for each violation ───────────────
        challans       = []
        final_viol_out = []
        h, w           = frame.shape[:2]

        for viol in all_violations:
            # OCR: find plate near violation bbox
            plate_result = self._find_best_plate(frame, viol["bbox"])

            plate_text = plate_result.cleaned_text if plate_result else "UNREAD"
            plate_conf = plate_result.ocr_conf     if plate_result else 0.0

            # CVCS score
            cvcs_result: CVCSResult = self.cvcs.score(
                model_conf       = viol["confidence"],
                frame_width      = w,
                frame_height     = h,
                lighting_score   = lighting,
                motion_magnitude = motion,
                camera_fp_rate   = self.profile.historical_fp,
                violation_type   = viol["violation_type"],
            )

            viol_out = {
                **viol,
                "plate":      plate_text,
                "plate_conf": plate_conf,
                "cvcs_score": cvcs_result.final_score,
                "decision":   cvcs_result.decision,
                "explanation":cvcs_result.explanation,
            }
            final_viol_out.append(viol_out)

            # ── Issue challan if warranted ─────────────────────────────────
            if cvcs_result.decision in ("auto_challan", "review"):
                plate_crop = plate_result.crop if plate_result else None
                record = self.challan_gen.create(
                    annotated_frame = annotated,
                    plate_crop      = plate_crop,
                    violation_type  = viol["violation_type"],
                    plate_text      = plate_text,
                    plate_conf      = plate_conf,
                    cvcs_score      = cvcs_result.final_score,
                    cvcs_decision   = cvcs_result.decision,
                    camera_meta     = self.camera_meta,
                    officer_id      = None,   # human review will fill this
                    extra_metadata  = {
                        "signal_state": signal_state,
                        "lighting":     lighting,
                        "motion":       round(motion, 4),
                        "explanation":  cvcs_result.explanation,
                    },
                )
                challans.append(record)

                # Annotate challan ID on the frame
                x1, y1 = viol["bbox"][:2]
                cv2.putText(annotated, f"CH: {record.challan_id}",
                            (x1, y1 - 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                            (255, 200, 0), 1)

        # ── Step 8: Update state for next frame ────────────────────────────
        self._prev_frame  = frame
        self._prev_bboxes = vehicle_bboxes

        processing_ms = (time.time() - t0) * 1000

        return FrameResult(
            frame_id        = self._frame_id,
            timestamp       = time.time(),
            annotated_frame = annotated,
            signal_state    = signal_state,
            violations      = final_viol_out,
            challans        = challans,
            processing_ms   = round(processing_ms, 1),
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  VIDEO FILE PROCESSING
    # ══════════════════════════════════════════════════════════════════════════

    def process_video(
        self,
        video_path:    str,
        output_path:   Optional[str] = None,
        skip_frames:   int = 0,        # process every Nth frame (0 = all)
        max_frames:    Optional[int] = None,
    ):
        """
        Generator that processes a video file frame-by-frame.

        Yields FrameResult for each processed frame.

        Args:
            video_path   : path to input video (.mp4, .avi, etc.)
            output_path  : if set, write annotated video to this path
            skip_frames  : skip N frames between each processed frame
                           (set to 2-4 for real-time performance on CPU)
            max_frames   : stop after this many frames (None = full video)

        Usage:
            pipeline = VisionEnforcePipeline(profile)
            for result in pipeline.process_video("traffic.mp4", "output.mp4"):
                print(f"Frame {result.frame_id}: {len(result.violations)} violations")
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        fps    = cap.get(cv2.CAP_PROP_FPS) or self.profile.fps
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        frame_count = 0
        processed   = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_count += 1

                if max_frames and processed >= max_frames:
                    break

                if skip_frames and (frame_count % (skip_frames + 1) != 0):
                    continue

                result = self.process_frame(frame, is_video=True)
                processed += 1

                if writer:
                    writer.write(result.annotated_frame)

                print(f"\rFrame {frame_count}/{total} | "
                      f"{len(result.violations)} violations | "
                      f"{result.processing_ms:.0f}ms", end="")

                yield result

        finally:
            cap.release()
            if writer:
                writer.release()
            print()

    # ══════════════════════════════════════════════════════════════════════════
    #  LIVE STREAM PROCESSING
    # ══════════════════════════════════════════════════════════════════════════

    def process_stream(self, camera_index: int = 0, rtsp_url: Optional[str] = None):
        """
        Generator for live camera stream processing.

        Args:
            camera_index : OpenCV camera index (0 = default webcam)
            rtsp_url     : RTSP stream URL for IP cameras
                           e.g. "rtsp://admin:password@192.168.1.100/stream1"

        Usage:
            for result in pipeline.process_stream(rtsp_url="rtsp://..."):
                cv2.imshow("VisionEnforce", result.annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        """
        source = rtsp_url if rtsp_url else camera_index
        cap    = cv2.VideoCapture(source)

        if not cap.isOpened():
            raise ConnectionError(f"Cannot open stream: {source}")

        # Reduce buffer size for lower latency on RTSP streams
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Stream ended or connection lost.")
                    break
                yield self.process_frame(frame, is_video=True)
        finally:
            cap.release()

    # ══════════════════════════════════════════════════════════════════════════
    #  SINGLE IMAGE PROCESSING
    # ══════════════════════════════════════════════════════════════════════════

    def process_image(self, image_path: str) -> FrameResult:
        """
        Process a single image file. Returns FrameResult.
        Perfect for batch-processing uploaded evidence images.
        """
        frame = cv2.imread(image_path)
        if frame is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        return self.process_frame(frame, is_video=False)

    # ══════════════════════════════════════════════════════════════════════════
    #  PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _find_best_plate(
        self,
        frame: np.ndarray,
        violation_bbox: Tuple[int, int, int, int],
    ) -> Optional[PlateResult]:
        """
        Find the license plate closest to the violation bounding box.
        Searches an expanded region around the violation for plate candidates.
        """
        x1, y1, x2, y2 = violation_bbox
        h, w = frame.shape[:2]

        # Expand search region by 50% in each direction
        expand = 0.5
        sx1 = max(0, int(x1 - (x2-x1)*expand))
        sy1 = max(0, int(y1 - (y2-y1)*expand))
        sx2 = min(w, int(x2 + (x2-x1)*expand))
        sy2 = min(h, int(y2 + (y2-y1)*expand))

        search_region = frame[sy1:sy2, sx1:sx2]
        if search_region.size == 0:
            return None

        # Detect plates in the region
        plates = self.ocr.find_plates(search_region)
        if not plates:
            return None

        # Run OCR on all plate candidates, return the highest-confidence valid result
        results = []
        for pb in plates:
            # Adjust bbox back to full-frame coordinates
            pb_full = (pb[0]+sx1, pb[1]+sy1, pb[2]+sx1, pb[3]+sy1)
            result  = self.ocr.extract(frame, pb_full)
            if result:
                results.append(result)

        if not results:
            return None

        # Prefer valid plates; among those, highest OCR confidence
        valid   = [r for r in results if r.is_valid]
        pool    = valid if valid else results
        return max(pool, key=lambda r: r.ocr_conf)

    @staticmethod
    def _merge_violations(
        yolo_violations: List[ViolationEvent],
        rule_violations: List[RuleViolation],
    ) -> List[dict]:
        """Normalise both violation types into a common dict format."""
        merged = []

        for v in yolo_violations:
            merged.append({
                "violation_type": v.violation_type,
                "confidence":     v.confidence,
                "bbox":           v.bbox,
                "source":         "yolo",
                "rider_count":    v.rider_count,
            })

        for v in rule_violations:
            merged.append({
                "violation_type": v.violation_type,
                "confidence":     v.confidence,
                "bbox":           v.bbox,
                "source":         "rule",
                "evidence":       v.evidence,
            })

        return merged

    @staticmethod
    def _draw_rule_violations(
        frame: np.ndarray,
        violations: List[RuleViolation],
    ) -> np.ndarray:
        """Draw orange boxes for rule-based violations (distinct from YOLO red)."""
        for v in violations:
            x1, y1, x2, y2 = v.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
            label = f"{v.violation_type} ({v.confidence:.2f})"
            cv2.rectangle(frame, (x1, y1-20), (x1+len(label)*8, y1),
                          (0, 140, 255), -1)
            cv2.putText(frame, label, (x1+2, y1-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        return frame

    @staticmethod
    def _draw_signal_state(frame: np.ndarray, state: str) -> np.ndarray:
        """Draw signal state indicator in top-right corner."""
        colours = {
            "red":     (0, 0, 220),
            "green":   (0, 200, 50),
            "amber":   (0, 165, 255),
            "unknown": (150, 150, 150),
        }
        colour = colours.get(state, (150, 150, 150))
        h, w   = frame.shape[:2]
        cx, cy = w - 40, 40
        cv2.circle(frame, (cx, cy), 18, colour, -1)
        cv2.circle(frame, (cx, cy), 18, (255, 255, 255), 2)
        cv2.putText(frame, state.upper()[:3], (cx-14, cy+5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        return frame


# ══════════════════════════════════════════════════════════════════════════════
#  DEMO — run pipeline on a single image or video
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VisionEnforce pipeline demo")
    parser.add_argument("--input",  required=True,
                        help="Path to image (.jpg/.png) or video (.mp4/.avi)")
    parser.add_argument("--output", default="output/demo_result.mp4",
                        help="Output path for annotated result")
    parser.add_argument("--camera-id",   default="CAM-000")
    parser.add_argument("--location",    default="Demo Intersection")
    parser.add_argument("--stop-line-y", type=int, default=None,
                        help="Y pixel of stop line (auto-calibrate if omitted)")
    args = parser.parse_args()

    # Build a minimal camera profile for the demo
    profile = CameraProfile(
        camera_id      = args.camera_id,
        location       = args.location,
        zone           = "Demo",
        stop_line_y    = args.stop_line_y,
        lane_boundary_x= None,    # wrong-side detection disabled if None
    )

    pipeline = VisionEnforcePipeline(profile)
    input_path = Path(args.input)

    if input_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
        # Single image
        result = pipeline.process_image(str(input_path))
        print(f"\n{'─'*50}")
        print(f"  Signal state : {result.signal_state}")
        print(f"  Violations   : {len(result.violations)}")
        for v in result.violations:
            print(f"    [{v['source'].upper():4}] {v['violation_type']:25} "
                  f"conf={v['confidence']:.2f}  "
                  f"CVCS={v['cvcs_score']:.2f}  "
                  f"→ {v['decision'].upper()}")
            if v.get("plate") and v["plate"] != "UNREAD":
                print(f"           Plate: {v['plate']} (OCR conf={v['plate_conf']:.2f})")
        print(f"  Challans     : {len(result.challans)}")
        for c in result.challans:
            print(f"    {c.challan_id}  ₹{c.fine_amount_inr}  "
                  f"hash={c.evidence_hash[:12]}...")
        print(f"  Time         : {result.processing_ms:.1f}ms")
        print(f"{'─'*50}")

        out_img = args.output.replace(".mp4", ".jpg")
        cv2.imwrite(out_img, result.annotated_frame)
        print(f"\n✓ Annotated image saved to: {out_img}")

    else:
        # Video
        total_violations = 0
        total_challans   = 0
        for result in pipeline.process_video(str(input_path), args.output, skip_frames=2):
            total_violations += len(result.violations)
            total_challans   += len(result.challans)

        print(f"\n✓ Processing complete")
        print(f"  Total violations detected : {total_violations}")
        print(f"  Total challans issued     : {total_challans}")
        print(f"  Annotated video saved to  : {args.output}")