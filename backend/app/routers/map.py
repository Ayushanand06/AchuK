
import logging
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Query

from app.settings import settings
from app.domain.analytics import AnalyticsEngine
from app.domain.map_integration import ViolationMapBuilder, MapplsAPIClient
from app.services import camera_registry, store

log = logging.getLogger("map")
router = APIRouter(prefix="/api/map", tags=["map"])
_engine = AnalyticsEngine()


@router.get("-data")
def map_data(shift: str = Query(default="evening")):
    """Full payload for the Mappls dashboard: pins, heatmap, routes, summary."""
    builder = ViolationMapBuilder(camera_registry.all_cameras())
    challans = store.all_challans()
    patrol = [asdict(r) for r in _engine.patrol_recommendations()]
    payload = builder.build_map_payload(challans, patrol, shift=shift)
    payload["mappls_configured"] = settings.mappls_configured
    return payload


@router.get("/cameras")
def cameras():
    """Registered camera nodes with coordinates."""
    return camera_registry.all_cameras()


@router.get("/nearby-police")
def nearby_police(lat: float, lng: float, radius_m: int = 3000):
    """Find police stations near a hotspot (requires Mappls credentials)."""
    if not settings.mappls_configured:
        raise HTTPException(status_code=503, detail="Mappls credentials not configured.")
    try:
        return MapplsAPIClient().find_nearby_police(lat, lng, radius_m)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Mappls error: {exc}")


@router.get("/geocode")
def geocode(address: str):
    """Geocode an address to coordinates (requires Mappls credentials)."""
    if not settings.mappls_configured:
        raise HTTPException(status_code=503, detail="Mappls credentials not configured.")
    try:
        coords = MapplsAPIClient().geocode(address)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Mappls error: {exc}")
    if not coords:
        raise HTTPException(status_code=404, detail="Address not found.")
    return {"lat": coords[0], "lng": coords[1]}
