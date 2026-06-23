# live.py — control + read the live camera-feed simulation.

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.settings import settings
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


@router.post("/focus/{camera_id}")
def focus(camera_id: str):
    """Process this camera at full frame-rate (the rest round-robin)."""
    return manager.set_focus(camera_id)


@router.get("/cameras/{camera_id}/frame.jpg")
def frame(camera_id: str):
    """Latest annotated frame as a single JPEG (snapshot)."""
    data = manager.latest_jpeg(camera_id)
    if not data:
        return Response(status_code=204)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/cameras/{camera_id}/stream.mjpg")
def stream(camera_id: str):
    """
    MJPEG stream (multipart/x-mixed-replace) of the camera's latest annotated
    frames — renders as smooth live video in an <img>. Repeats the latest frame
    up to live_target_fps, so playback is as smooth as the processing rate.
    """
    boundary = "frame"
    delay = 1.0 / max(1, settings.live_target_fps)

    async def gen():
        last = None
        while manager.running:
            data = manager.latest_jpeg(camera_id)
            if data is not None and data is not last:
                last = data
            if last is not None:
                yield (b"--" + boundary.encode() + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(last)).encode() + b"\r\n\r\n"
                       + last + b"\r\n")
            await asyncio.sleep(delay)

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store"},
    )
