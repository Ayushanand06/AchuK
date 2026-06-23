
from datetime import datetime, timedelta
from dataclasses import asdict
from fastapi import APIRouter

from app.domain.analytics import AnalyticsEngine
from app.services import store, camera_registry

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
_engine = AnalyticsEngine()


@router.get("/weekly")
def weekly_report():
    """Totals, revenue, by-type / by-zone / by-hour / by-day, week-on-week."""
    return _engine.weekly_report()


@router.get("/kpis")
def enforcement_kpis():
    """Enforcement KPIs (auto-challan rate, OCR accuracy, uptime, ...)."""
    return _engine.enforcement_kpis()


@router.get("/patrol")
def patrol_recommendations():
    """Predictive patrol deployment recommendations for the next 6 hours."""
    return [asdict(r) for r in _engine.patrol_recommendations()]


@router.get("/camera-fp")
def camera_false_positive_rates():
    """Per-camera false-positive rate over the last 30 days."""
    return _engine.camera_false_positive_rates()


@router.get("/zone-hour")
def zone_hour_matrix():
    """Zone × 24-hour violation intensity matrix for the heatmap."""
    return _engine.zone_hour_matrix()


@router.get("/buckets")
def decision_buckets():
    """Decision buckets (auto / review / discarded) for the operations cards."""
    return _engine.buckets()


@router.get("/camera-report")
def camera_report():
    """
    Per-camera table for the analytics dashboard: 7-day event count, false-
    positive rate, zone, and a derived status (ok / watch / flag).
    """
    cutoff = (datetime.utcnow().date() - timedelta(days=7)).isoformat()
    events: dict = {}
    for rec in store.all_challans():
        if rec.get("timestamp", "")[:10] < cutoff:
            continue
        cam = rec.get("camera_id", "UNKNOWN")
        events[cam] = events.get(cam, 0) + 1

    fp_rates = _engine.camera_false_positive_rates()
    cameras = camera_registry.all_cameras()

    rows = []
    cam_ids = set(events) | set(fp_rates) | set(cameras)
    for cam_id in cam_ids:
        cam = cameras.get(cam_id, {})
        fp_pct = round(fp_rates.get(cam_id, 0.0) * 100, 1)
        status = "flag" if fp_pct >= 4 else "watch" if fp_pct >= 2.5 else "ok"
        rows.append({
            "id":       cam_id,
            "zone":     cam.get("zone") or cam.get("location") or "Unknown",
            "events":   events.get(cam_id, 0),
            "fp":       fp_pct,
            "status":   status,
        })

    rows.sort(key=lambda r: r["events"], reverse=True)
    return {"cameras": rows}
