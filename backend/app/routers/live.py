# live.py — control + read the live camera-feed simulation.

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.services.live_feed import manager

router = APIRouter(prefix="/api/live", tags=["live"])


@router.post("/start")
def start():
    try:
        return manager.start()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/stop")
def stop():
    return manager.stop()


@router.get("/status")
def status():
    return manager.status()


@router.get("/cameras/{camera_id}/frame.jpg")
def frame(camera_id: str):
    path = manager.frame_path(camera_id)
    if not path:
        # 204 = no frame yet (feeds not started or camera idle).
        return Response(status_code=204)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
