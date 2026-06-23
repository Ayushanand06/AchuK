
from fastapi import APIRouter, HTTPException

from app.services import jobs as job_store

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(limit: int = 50):
    return {"jobs": job_store.list_jobs(limit=limit)}


@router.get("/{job_id}")
def get_job(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job
