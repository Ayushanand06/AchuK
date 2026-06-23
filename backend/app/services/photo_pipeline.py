
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.domain.preprocessing import ImagePreprocessor
from app.domain.ocr import PlateResult
from app.domain.cvcs import CVCSEngine, CVCSResult
from app.domain.challan import ChallanGenerator, ChallanRecord
from app.services.inference import get_detector, get_ocr
from app.services import camera_registry

log = logging.getLogger("photo_pipeline")


@dataclass
class PhotoResult:
    """Everything produced for one processed image."""
    violations:    List[dict]
    challans:      List[ChallanRecord]
    annotated:     np.ndarray
    processing_ms: float
    camera_id:     str


class PhotoPipeline:
    """Stateless per-image pipeline. Heavy objects come from the inference cache."""

    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self.detector     = get_detector()
        self.ocr          = get_ocr()
        self.cvcs         = CVCSEngine()
        self.challan_gen  = ChallanGenerator()

    def process(self, raw_frame: np.ndarray, camera_id: Optional[str] = None) -> PhotoResult:
        t0 = time.time()
        meta = camera_registry.camera_meta(camera_id)

        frame = self.preprocessor.process(raw_frame, is_video=False)
        lighting = self.preprocessor.lighting_score(frame)
        h, w = frame.shape[:2]

        violations, annotated = self.detector.detect(frame, meta)

        challans: List[ChallanRecord] = []
        out_violations: List[dict] = []

        for viol in violations:
            plate = self._find_best_plate(frame, viol.bbox)
            plate_text = plate.cleaned_text if plate else "UNREAD"
            plate_conf = plate.ocr_conf if plate else 0.0

            cvcs: CVCSResult = self.cvcs.score(
                model_conf=viol.confidence,
                frame_width=w,
                frame_height=h,
                lighting_score=lighting,
                motion_magnitude=0.0,
                camera_fp_rate=meta["historical_fp"],
                violation_type=viol.violation_type,
            )

            record = None
            if cvcs.decision in ("auto_challan", "review"):
                record = self.challan_gen.create(
                    annotated_frame=annotated,
                    plate_crop=plate.crop if plate else None,
                    violation_type=viol.violation_type,
                    plate_text=plate_text,
                    plate_conf=plate_conf,
                    cvcs_score=cvcs.final_score,
                    cvcs_decision=cvcs.decision,
                    camera_meta=meta,
                    officer_id=None,
                    extra_metadata={
                        "lighting": round(lighting, 4),
                        "explanation": cvcs.explanation,
                        "source": "photo",
                        "cvcs_factors": {
                            "model_conf": cvcs.model_conf,
                            "resolution": cvcs.resolution_score,
                            "lighting": cvcs.lighting_score,
                            "speed": cvcs.speed_score,
                            "camera_trust": cvcs.camera_score,
                        },
                    },
                )
                challans.append(record)

            out_violations.append({
                "violation_type": viol.violation_type,
                "confidence":     round(viol.confidence, 4),
                "bbox":           list(viol.bbox),
                "rider_count":    viol.rider_count,
                "plate":          plate_text,
                "plate_conf":     round(plate_conf, 4),
                "cvcs_score":     cvcs.final_score,
                "decision":       cvcs.decision,
                "explanation":    cvcs.explanation,
                "fine_amount_inr": record.fine_amount_inr if record else None,
                "challan_id":     record.challan_id if record else None,
            })

        return PhotoResult(
            violations=out_violations,
            challans=challans,
            annotated=annotated,
            processing_ms=round((time.time() - t0) * 1000, 1),
            camera_id=meta["camera_id"],
        )


    def _find_best_plate(
        self,
        frame: np.ndarray,
        violation_bbox: Tuple[int, int, int, int],
    ) -> Optional[PlateResult]:
        """Find the license plate closest to the violation bbox."""
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

        crop = self.ocr.crop_plate(frame, best_box) if best_box else None
        if crop is None:
            return None
        return PlateResult(raw_text="", cleaned_text="UNREAD", is_valid=False,
                           ocr_conf=0.0, bbox=best_box, crop=crop)


_PIPELINE: Optional[PhotoPipeline] = None


def get_pipeline() -> PhotoPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = PhotoPipeline()
    return _PIPELINE
