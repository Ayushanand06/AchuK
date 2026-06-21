# violations.py — image / video upload -> detection -> challan.

import logging
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks

from app.settings import settings
from app.config import VIDEO_SKIP_FRAMES
from app.schemas.responses import DetectResponse, ViolationOut, VideoJobAccepted
from app.services.photo_pipeline import get_pipeline
from app.services import store, jobs

log = logging.getLogger("violations")
router = APIRouter(prefix="/api/violations", tags=["violations"])


@router.post("/detect", response_model=DetectResponse)
async def detect(
    file: UploadFile = File(..., description="Traffic photo (jpg/png)"),
    camera_id: str | None = Form(default=None, description="Registered camera id"),
):
    """Run the photo pipeline on an uploaded image and issue challans."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    try:
        result = get_pipeline().process(frame, camera_id=camera_id)
    except Exception as exc:  # surface model/inference errors cleanly
        log.exception("Detection failed")
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}")

    # Evidence URL from the first issued challan (all share one annotated frame).
    evidence_url = None
    if result.challans:
        evidence_url = store.evidence_url(
            {
                "image_path": result.challans[0].image_path,
                "timestamp": result.challans[0].timestamp,
                "challan_id": result.challans[0].challan_id,
            }
        )

    return DetectResponse(
        camera_id=result.camera_id,
        processing_ms=result.processing_ms,
        violation_count=len(result.violations),
        challan_count=len(result.challans),
        violations=[ViolationOut(**v) for v in result.violations],
        evidence_url=evidence_url,
    )


@router.post("/detect-video", response_model=VideoJobAccepted)
async def detect_video(
    background: BackgroundTasks,
    file: UploadFile = File(..., description="Traffic video clip (mp4/avi)"),
    camera_id: str | None = Form(default=None, description="Registered camera id"),
    skip_frames: int = Form(default=VIDEO_SKIP_FRAMES, description="Process every (N+1)th frame"),
    max_frames: int | None = Form(default=None, description="Cap processed frames"),
):
    """
    Upload a video for asynchronous processing. Returns a job_id immediately;
    poll GET /api/jobs/{job_id} for progress and results. Time-dependent
    violations (red-light, stop-line, wrong-side, parking) require the camera to
    be calibrated first (see /api/cameras/{id}/calibration).
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "clip.mp4").suffix or ".mp4"
    saved = uploads / f"{uuid.uuid4().hex}{suffix}"
    saved.write_bytes(raw)

    job_id = jobs.create_job(camera_id, file.filename or saved.name)
    background.add_task(
        jobs.run_job, job_id, str(saved), camera_id, skip_frames, max_frames,
    )
    return VideoJobAccepted(
        job_id=job_id, status="queued", camera_id=camera_id,
        poll_url=f"/api/jobs/{job_id}",
    )
