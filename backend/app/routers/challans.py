# challans.py — searchable challan records + single-record lookup + review action.

from fastapi import APIRouter, HTTPException, Query

from app.schemas.responses import ChallanListResponse, ChallanOut, ReviewIn
from app.services import store

router = APIRouter(prefix="/api/challans", tags=["challans"])


@router.get("", response_model=ChallanListResponse)
def list_challans(
    violation_type: str | None = Query(default=None),
    zone: str | None = Query(default=None, description="camera_location"),
    plate: str | None = Query(default=None, description="partial plate match"),
    decision: str | None = Query(default=None, description="auto_challan|review"),
    date: str | None = Query(default=None, description="YYYY-MM-DD"),
    pending_review: bool = Query(default=False, description="only un-actioned review cases"),
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    records = store.list_challans(
        violation_type=violation_type, zone=zone, plate=plate,
        decision=decision, date=date, pending_review=pending_review,
        limit=limit, offset=offset,
    )
    results = [ChallanOut(**store.to_challan_out(r)) for r in records]
    return ChallanListResponse(count=len(results), results=results)


@router.get("/{challan_id}", response_model=ChallanOut)
def get_challan(challan_id: str):
    rec = store.get_challan(challan_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Challan not found.")
    out = store.to_challan_out(rec)
    out["review"] = store.review_status(challan_id)
    return ChallanOut(**out)


@router.post("/{challan_id}/review", response_model=ChallanOut)
def review_challan(challan_id: str, body: ReviewIn):
    """Record an officer's review decision (issue / reject / escalate)."""
    if body.action not in ("issue", "reject", "escalate"):
        raise HTTPException(status_code=400, detail="Invalid action.")
    rec = store.get_challan(challan_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Challan not found.")
    review = store.save_review(
        challan_id, body.action, body.corrected_plate, body.officer_id,
    )
    out = store.to_challan_out(rec)
    out["review"] = review
    return ChallanOut(**out)
