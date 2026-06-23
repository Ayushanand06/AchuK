
import logging
import tempfile
from pathlib import Path

import cv2
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.settings import settings
from app.schemas.responses import Calibration, FrameGrabResponse
from app.services import camera_registry

log = logging.getLogger("cameras")
router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.post("/{camera_id}/frame-grab", response_model=FrameGrabResponse)
async def frame_grab(camera_id: str, file: UploadFile = File(...)):
    """Extract a frame from an uploaded clip so you can read off pixel coords."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    tmp = Path(tempfile.gettempdir()) / f"grab_{camera_id}_{file.filename}"
    tmp.write_bytes(raw)
    try:
        cap = cv2.VideoCapture(str(tmp))
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Could not open video.")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps))
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise HTTPException(status_code=400, detail="Could not read a frame.")
    finally:
        tmp.unlink(missing_ok=True)

    frames_dir = Path(settings.frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    out = frames_dir / f"{camera_id}.jpg"
    cv2.imwrite(str(out), frame)
    h, w = frame.shape[:2]
    return FrameGrabResponse(
        camera_id=camera_id, frame_url=f"/frames/{camera_id}.jpg", width=w, height=h,
    )


@router.get("/{camera_id}/calibration", response_model=Calibration)
def get_calibration(camera_id: str):
    return Calibration(**camera_registry.get_calibration(camera_id))


@router.put("/{camera_id}/calibration", response_model=Calibration)
def put_calibration(camera_id: str, calibration: Calibration):
    saved = camera_registry.save_calibration(camera_id, calibration.model_dump())
    return Calibration(**saved)
