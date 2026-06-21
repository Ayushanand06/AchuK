# jobs.py — in-memory background job tracker for video processing.
#
# Prototype-grade: jobs live in process memory and are lost on restart. Enough
# for a single-instance demo; a DB/queue would be the production upgrade.

import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict

from app.settings import settings

log = logging.getLogger("jobs")

JOBS: Dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(camera_id: Optional[str], filename: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",          # queued | running | done | error
        "progress": 0.0,             # 0.0 – 1.0
        "frames_done": 0,
        "frames_total": 0,
        "camera_id": camera_id,
        "filename": filename,
        "result": None,
        "error": None,
        "video_url": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    return JOBS.get(job_id)


def list_jobs(limit: int = 50) -> list:
    jobs = sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)
    return jobs[:limit]


def _update(job_id: str, **fields):
    job = JOBS.get(job_id)
    if not job:
        return
    job.update(fields)
    job["updated_at"] = _now()


def run_job(job_id: str, video_path: str, camera_id: Optional[str],
            skip_frames: int, max_frames: Optional[int]):
    """Executed in a background thread. Updates JOBS as it progresses."""
    from app.services.video_pipeline import VideoPipeline

    _update(job_id, status="running")
    out_path = str(Path(settings.videos_dir) / f"{job_id}.mp4")
    Path(settings.videos_dir).mkdir(parents=True, exist_ok=True)

    def progress(done: int, total: int):
        pct = (done / total) if total else 0.0
        _update(job_id, frames_done=done, frames_total=total,
                progress=round(min(pct, 1.0), 4))

    try:
        pipeline = VideoPipeline(camera_id, progress_cb=progress)
        result = pipeline.process(
            video_path, out_path, skip_frames=skip_frames, max_frames=max_frames,
        )
        _update(
            job_id, status="done", progress=1.0, result=result,
            video_url=f"/videos/{job_id}.mp4",
        )
        log.info("Job %s done: %s", job_id, result.get("by_type"))
    except Exception as exc:
        log.exception("Job %s failed", job_id)
        _update(job_id, status="error", error=str(exc))
    finally:
        # Best-effort cleanup of the uploaded source clip.
        try:
            Path(video_path).unlink(missing_ok=True)
        except Exception:
            pass
