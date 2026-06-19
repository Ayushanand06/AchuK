# challan.py — Evidence packet generation with tamper-evident hashing
# Produces legally defensible challan records

import cv2
import json
import hashlib
import uuid
import os
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

from config import (
    OUTPUT_DIR, EVIDENCE_IMAGE_QUALITY,
    HASH_ALGORITHM, FINE_AMOUNTS
)


@dataclass
class ChallanRecord:
    """
    Immutable evidence record for one traffic violation.
    All fields are hashed together to produce a tamper-evident digest.
    """
    challan_id:       str
    timestamp:        str
    violation_type:   str
    plate_number:     str
    plate_confidence: float
    cvcs_score:       float
    cvcs_decision:    str
    camera_id:        str
    camera_location:  str
    fine_amount_inr:  int
    officer_id:       Optional[str]
    image_path:       str
    plate_crop_path:  str
    evidence_hash:    str = field(default="")
    metadata:         dict = field(default_factory=dict)


class ChallanGenerator:
    """
    Generates, saves, and hashes evidence packets for traffic violations.

    Each packet contains:
      1. Annotated full frame (bounding boxes + labels)
      2. Upscaled plate crop
      3. JSON metadata with all violation details
      4. SHA-256 hash over all fields (tamper-evident)

    Directory structure:
        output/challans/YYYY-MM-DD/<challan_id>/
            evidence.jpg
            plate_crop.jpg
            record.json
    """

    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def create(
        self,
        annotated_frame: np.ndarray,
        plate_crop:      Optional[np.ndarray],
        violation_type:  str,
        plate_text:      str,
        plate_conf:      float,
        cvcs_score:      float,
        cvcs_decision:   str,
        camera_meta:     dict,
        officer_id:      Optional[str] = None,
        extra_metadata:  dict = None,
    ) -> ChallanRecord:
        challan_id = self._new_id()
        timestamp  = datetime.utcnow().isoformat() + "Z"
        date_str   = datetime.utcnow().strftime("%Y-%m-%d")

        out_dir = os.path.join(OUTPUT_DIR, date_str, challan_id)
        os.makedirs(out_dir, exist_ok=True)

        img_path   = os.path.join(out_dir, "evidence.jpg")
        plate_path = os.path.join(out_dir, "plate_crop.jpg")

        watermarked = self._annotate_watermark(annotated_frame, challan_id)
        self._save_image(watermarked, img_path)
        if plate_crop is not None:
            self._save_image(plate_crop, plate_path)
        else:
            plate_path = ""

        record = ChallanRecord(
            challan_id       = challan_id,
            timestamp        = timestamp,
            violation_type   = violation_type,
            plate_number     = plate_text,
            plate_confidence = round(plate_conf, 4),
            cvcs_score       = round(cvcs_score, 4),
            cvcs_decision    = cvcs_decision,
            camera_id        = camera_meta.get("camera_id", "UNKNOWN"),
            camera_location  = camera_meta.get("location", "Unknown"),
            fine_amount_inr  = FINE_AMOUNTS.get(violation_type, 500),
            officer_id       = officer_id,
            image_path       = img_path,
            plate_crop_path  = plate_path,
            metadata         = extra_metadata or {},
        )

        record.evidence_hash = self._hash_record(record)
        json_path = os.path.join(out_dir, "record.json")
        self._save_json(record, json_path)
        return record

    def verify(self, record: ChallanRecord) -> bool:
        """Re-compute hash — returns False if record was tampered with."""
        stored = record.evidence_hash
        record.evidence_hash = ""
        computed = self._hash_record(record)
        record.evidence_hash = stored
        return computed == stored

    def load(self, challan_id: str, date_str: str) -> Optional[ChallanRecord]:
        path = os.path.join(OUTPUT_DIR, date_str, challan_id, "record.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return ChallanRecord(**json.load(f))

    # ── Watermark ──────────────────────────────────────────────────────────────

    @staticmethod
    def _annotate_watermark(img: np.ndarray, challan_id: str) -> np.ndarray:
        out = img.copy()
        h, w = out.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.rectangle(out, (0, h - 36), (w, h), (20, 20, 20), -1)
        cv2.putText(out, f"VisionEnforce  |  Challan: {challan_id}",
                    (8, h - 20), font, 0.45, (200, 200, 200), 1)
        cv2.putText(out, "OFFICIAL TRAFFIC VIOLATION EVIDENCE",
                    (8, h - 6), font, 0.38, (100, 180, 255), 1)
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        cv2.putText(out, ts, (w - 230, 18), font, 0.40, (200, 200, 200), 1)
        return out

    # ── Hashing ────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash_record(record: ChallanRecord) -> str:
        d = asdict(record)
        d.pop("evidence_hash", None)
        canonical = json.dumps(d, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    # ── Storage ────────────────────────────────────────────────────────────────

    @staticmethod
    def _save_image(img: np.ndarray, path: str):
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, EVIDENCE_IMAGE_QUALITY])

    @staticmethod
    def _save_json(record: ChallanRecord, path: str):
        with open(path, "w") as f:
            json.dump(asdict(record), f, indent=2, ensure_ascii=True)

    @staticmethod
    def _new_id() -> str:
        date = datetime.utcnow().strftime("%Y%m%d")
        uid  = uuid.uuid4().hex[:8].upper()
        return f"VE-{date}-{uid}"