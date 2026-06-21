# responses.py — Pydantic response models for the API.

from typing import List, Optional, Any
from pydantic import BaseModel


class ViolationOut(BaseModel):
    violation_type: str
    confidence: float
    bbox: List[int]
    rider_count: int
    plate: str
    plate_conf: float
    cvcs_score: float
    decision: str
    explanation: str
    fine_amount_inr: Optional[int] = None
    challan_id: Optional[str] = None


class DetectResponse(BaseModel):
    camera_id: str
    processing_ms: float
    violation_count: int
    challan_count: int
    violations: List[ViolationOut]
    evidence_url: Optional[str] = None


class ChallanOut(BaseModel):
    challan_id: str
    timestamp: str
    violation_type: str
    plate_number: str
    plate_confidence: float
    cvcs_score: float
    cvcs_decision: str
    camera_id: str
    camera_location: str
    fine_amount_inr: int
    evidence_hash: str
    evidence_url: Optional[str] = None
    plate_crop_url: Optional[str] = None
    metadata: dict = {}
    review: Optional[dict] = None


class ReviewIn(BaseModel):
    action: str                              # issue | reject | escalate
    corrected_plate: Optional[str] = None
    officer_id: Optional[str] = None


class ChallanListResponse(BaseModel):
    count: int
    results: List[ChallanOut]


class HealthResponse(BaseModel):
    status: str
    mappls_configured: bool
    models: Optional[Any] = None


class VideoJobAccepted(BaseModel):
    job_id: str
    status: str
    camera_id: Optional[str] = None
    poll_url: str


class Calibration(BaseModel):
    stop_line_y: Optional[int] = None
    signal_roi: Optional[List[int]] = None          # [x1, y1, x2, y2]
    lane_boundary_x: Optional[int] = None
    expected_left_dx: float = 1.0
    no_parking_zones: List[List[List[int]]] = []     # [[[x,y], ...], ...]
    fps: Optional[float] = None


class FrameGrabResponse(BaseModel):
    camera_id: str
    frame_url: str
    width: int
    height: int
