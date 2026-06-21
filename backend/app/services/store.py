# store.py — read-side access to the file-based challan store.
#
# Records are written by ChallanGenerator to:
#   {OUTPUT_DIR}/YYYY-MM-DD/<challan_id>/record.json   (+ evidence.jpg, plate_crop.jpg)
# This module scans that tree for listing, filtering and single-record lookup.

import json
import logging
from pathlib import Path
from typing import List, Optional

from app.config import OUTPUT_DIR

log = logging.getLogger("store")


def _iter_record_paths():
    base = Path(OUTPUT_DIR)
    if not base.exists():
        return
    # newest date dirs first
    for date_dir in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        for rec_dir in date_dir.iterdir():
            rec = rec_dir / "record.json"
            if rec.exists():
                yield rec


def list_challans(
    violation_type: Optional[str] = None,
    zone: Optional[str] = None,
    plate: Optional[str] = None,
    decision: Optional[str] = None,
    date: Optional[str] = None,          # YYYY-MM-DD
    pending_review: bool = False,        # decision == review AND not yet actioned
    limit: int = 200,
    offset: int = 0,
) -> List[dict]:
    """Return challan record dicts matching the given filters, newest first."""
    out: List[dict] = []
    for path in _iter_record_paths():
        if date and path.parent.parent.name != date:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if violation_type and rec.get("violation_type") != violation_type:
            continue
        if zone and rec.get("camera_location") != zone:
            continue
        if decision and rec.get("cvcs_decision") != decision:
            continue
        if plate and plate.upper().replace(" ", "") not in \
                str(rec.get("plate_number", "")).upper().replace(" ", ""):
            continue
        if pending_review:
            if rec.get("cvcs_decision") != "review":
                continue
            if (path.parent / "review.json").exists():
                continue
        out.append(rec)

    # sort newest first by timestamp, then page
    out.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return out[offset:offset + limit]


def all_challans() -> List[dict]:
    """Every record (used by analytics/map builders)."""
    return list_challans(limit=10_000_000)


def get_challan(challan_id: str) -> Optional[dict]:
    for path in _iter_record_paths():
        if path.parent.name == challan_id:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def _challan_dir(challan_id: str) -> Optional[Path]:
    for path in _iter_record_paths():
        if path.parent.name == challan_id:
            return path.parent
    return None


def review_status(challan_id: str) -> Optional[dict]:
    """Return the saved officer review (sidecar) for a challan, or None."""
    d = _challan_dir(challan_id)
    if not d:
        return None
    sidecar = d / "review.json"
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_review(challan_id: str, action: str, corrected_plate: Optional[str] = None,
                officer_id: Optional[str] = None) -> Optional[dict]:
    """
    Persist an officer's review decision as a `review.json` sidecar next to the
    record — never mutating the hashed record.json, so the evidence hash stays
    valid. Returns the saved sidecar, or None if the challan doesn't exist.
    """
    from datetime import datetime, timezone
    d = _challan_dir(challan_id)
    if not d:
        return None
    sidecar = {
        "challan_id": challan_id,
        "action": action,                      # issue | reject | escalate
        "corrected_plate": corrected_plate,
        "officer_id": officer_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    (d / "review.json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return sidecar


def evidence_url(record: dict) -> Optional[str]:
    """
    Build a public URL for a record's evidence image. OUTPUT_DIR is mounted at
    /evidence, so the URL is /evidence/<path-relative-to-OUTPUT_DIR>.
    """
    img_path = record.get("image_path")
    if not img_path:
        return None
    try:
        rel = Path(img_path).resolve().relative_to(Path(OUTPUT_DIR).resolve())
    except Exception:
        # Fall back to reconstructing from date + challan_id.
        ts = record.get("timestamp", "")
        date = ts[:10] if ts else ""
        cid = record.get("challan_id", "")
        if not (date and cid):
            return None
        rel = Path(date) / cid / "evidence.jpg"
    return "/evidence/" + str(rel).replace("\\", "/")


def _media_url(path: Optional[str]) -> Optional[str]:
    """Map an absolute path under OUTPUT_DIR to its /evidence/... URL."""
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(Path(OUTPUT_DIR).resolve())
    except Exception:
        return None
    return "/evidence/" + str(rel).replace("\\", "/")


def to_challan_out(record: dict) -> dict:
    """Project a stored record into the API ChallanOut shape (+ media URLs)."""
    return {
        "challan_id":       record.get("challan_id", ""),
        "timestamp":        record.get("timestamp", ""),
        "violation_type":   record.get("violation_type", ""),
        "plate_number":     record.get("plate_number", "UNREAD"),
        "plate_confidence": record.get("plate_confidence", 0.0),
        "cvcs_score":       record.get("cvcs_score", 0.0),
        "cvcs_decision":    record.get("cvcs_decision", ""),
        "camera_id":        record.get("camera_id", ""),
        "camera_location":  record.get("camera_location", ""),
        "fine_amount_inr":  record.get("fine_amount_inr", 0),
        "evidence_hash":    record.get("evidence_hash", ""),
        "evidence_url":     evidence_url(record),
        "plate_crop_url":   _media_url(record.get("plate_crop_path")),
        "metadata":         record.get("metadata", {}),
    }
