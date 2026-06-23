
import sys
import json
import uuid
import random
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timedelta

import cv2
import numpy as np

from app.config import OUTPUT_DIR, FINE_AMOUNTS
from app.services import camera_registry

random.seed(42)

VIOLATION_WEIGHTS = [
    ("No helmet", 30), ("Stop-line violation", 16), ("No seatbelt", 14),
    ("Red-light run", 12), ("Triple riding", 10), ("Wrong-side driving", 10),
    ("Illegal parking", 8),
]
HIGH_STAKES = {"Red-light run", "Wrong-side driving"}
STATES = ["KA", "TN", "AP", "TS", "MH", "KL", "DL"]


def random_plate():
    s = random.choice(STATES)
    letters = "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(random.choice([1, 2])))
    return f"{s} {random.randint(1, 99):02d} {letters} {random.randint(1, 9999):04d}"


def hash_record(d: dict) -> str:
    dd = dict(d)
    dd.pop("evidence_hash", None)
    return hashlib.sha256(json.dumps(dd, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def make_evidence(path, vtype, cam_id, plate):
    img = np.full((720, 1280, 3), 26, np.uint8)
    cv2.rectangle(img, (380, 230), (760, 560), (0, 0, 210), 3)
    cv2.putText(img, f"VIOLATION: {vtype}", (380, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 210), 2)
    cv2.putText(img, f"{cam_id}  plate {plate}", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
    cv2.rectangle(img, (0, 684), (1280, 720), (20, 20, 20), -1)
    cv2.putText(img, "VisionEnforce  |  OFFICIAL TRAFFIC VIOLATION EVIDENCE (demo seed)",
                (8, 708), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 255), 1)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def make_plate_crop(path, plate):
    img = np.full((72, 300, 3), 235, np.uint8)
    cv2.rectangle(img, (2, 2), (297, 69), (40, 40, 40), 2)
    cv2.putText(img, plate.replace(" ", ""), (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 92])


def write_record(rec: dict, date_str: str, evidence=False, sidecar_action=None):
    out_dir = Path(OUTPUT_DIR) / date_str / rec["challan_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    if evidence:
        img_path = out_dir / "evidence.jpg"
        crop_path = out_dir / "plate_crop.jpg"
        make_evidence(img_path, rec["violation_type"], rec["camera_id"], rec["plate_number"])
        make_plate_crop(crop_path, rec["plate_number"])
        rec["image_path"] = str(img_path)
        rec["plate_crop_path"] = str(crop_path)
    rec["evidence_hash"] = hash_record(rec)
    (out_dir / "record.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    if sidecar_action:
        (out_dir / "review.json").write_text(json.dumps({
            "challan_id": rec["challan_id"], "action": sidecar_action,
            "corrected_plate": rec["plate_number"], "officer_id": "seed",
            "reviewed_at": rec["timestamp"],
        }, indent=2), encoding="utf-8")


def main():
    keep = "--keep" in sys.argv
    base = Path(OUTPUT_DIR)
    if not keep and base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)

    cams = list(camera_registry.all_cameras().values())
    if not cams:
        print("No cameras in registry."); return
    peak_hours = [8, 11, 14, 18, 20, 22]
    peaks = {c["camera_id"]: peak_hours[i % len(peak_hours)] for i, c in enumerate(cams)}

    now = datetime.utcnow()
    total = 0
    review_recent = []

    for day in range(28):
        date = (now - timedelta(days=day)).date()
        for cam in cams:
            cam_id = cam["camera_id"]
            n = random.randint(5, 13)
            for _ in range(n):
                vtype = random.choices([v for v, _ in VIOLATION_WEIGHTS],
                                       weights=[w for _, w in VIOLATION_WEIGHTS])[0]
                hour = int(round(random.gauss(peaks[cam_id], 2.5))) % 24
                ts = datetime(date.year, date.month, date.day, hour,
                              random.randint(0, 59), random.randint(0, 59),
                              random.randint(0, 999) * 1000)
                if vtype in HIGH_STAKES:
                    review = random.random() < 0.55
                else:
                    review = random.random() < 0.25
                cvcs = round(random.uniform(0.55, 0.79) if review else random.uniform(0.80, 0.97), 4)
                decision = "review" if review else "auto_challan"
                unread = random.random() < 0.30
                plate = "UNREAD" if unread else random_plate()
                rec = {
                    "challan_id": f"VE-{ts.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
                    "violation_type": vtype,
                    "plate_number": plate,
                    "plate_confidence": 0.0 if unread else round(random.uniform(0.62, 0.97), 4),
                    "cvcs_score": cvcs,
                    "cvcs_decision": decision,
                    "camera_id": cam_id,
                    "camera_location": cam.get("location", "Unknown"),
                    "fine_amount_inr": FINE_AMOUNTS.get(vtype, 500),
                    "officer_id": None,
                    "image_path": "",
                    "plate_crop_path": "",
                    "metadata": {"source": "seed"},
                }
                date_str = ts.strftime("%Y-%m-%d")
                if decision == "review" and day <= 1 and len(review_recent) < 14:
                    rec["metadata"].update({
                        "explanation": _explain(vtype),
                        "cvcs_factors": _factors(cvcs),
                    })
                    write_record(rec, date_str, evidence=True)
                    review_recent.append(rec["challan_id"])
                else:
                    write_record(rec, date_str,
                                 sidecar_action="issue" if decision == "review" else None)
                total += 1

    print(f"Seeded {total} challans across {len(cams)} cameras over 28 days.")
    print(f"Imaged review-queue cases: {len(review_recent)}")
    print(f"Output: {OUTPUT_DIR}")


def _factors(cvcs):
    base = max(0.4, min(0.95, cvcs))
    jit = lambda: round(min(0.98, max(0.35, base + random.uniform(-0.2, 0.15))), 2)
    return {"model_conf": jit(), "resolution": jit(), "lighting": jit(),
            "speed": jit(), "camera_trust": jit()}


def _explain(vtype):
    return (f"Routed to review: borderline CVCS for {vtype.lower()}. "
            "Weakest factor flagged below — confirm plate from the snapshot and decide.")


if __name__ == "__main__":
    main()
