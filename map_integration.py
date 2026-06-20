# map_integration.py — MapMyIndia (Mappls) full traffic intelligence integration
#
# ─────────────────────────────────────────────────────────────────────────────
# SETUP: Get your free API key from https://apis.mappls.com
# Add to config.py:
#   MAPMYINDIA_API_KEY     = "your_rest_api_key"
#   MAPMYINDIA_CLIENT_ID   = "your_client_id"       # for OAuth token
#   MAPMYINDIA_CLIENT_SECRET = "your_client_secret"
# ─────────────────────────────────────────────────────────────────────────────
#
# APIs used in this file:
#   1. Mappls Maps JS SDK         → interactive map rendering
#   2. Mappls Geocoding API       → camera address → lat/lng
#   3. Mappls Reverse Geocoding   → lat/lng → road name / zone
#   4. Mappls Route API           → diversion route suggestions
#   5. Mappls Traffic API         → live traffic overlay
#   6. Mappls Nearby API          → find police stations near hotspot
#
# All API docs: https://developer.mappls.com/mapping/maps-api/

import json
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

# ── Internal imports ──────────────────────────────────────────────────────────
try:
    from config import (
        MAPMYINDIA_API_KEY,
        MAPMYINDIA_CLIENT_ID,
        MAPMYINDIA_CLIENT_SECRET,
    )
except ImportError:
    MAPMYINDIA_API_KEY      = "YOUR_API_KEY_HERE"
    MAPMYINDIA_CLIENT_ID    = "YOUR_CLIENT_ID_HERE"
    MAPMYINDIA_CLIENT_SECRET= "YOUR_CLIENT_SECRET_HERE"


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class ViolationPin:
    """
    A single violation event to be plotted on the map.
    Produced by ChallanRecord + camera GPS coordinates.
    """
    challan_id:     str
    lat:            float
    lng:            float
    violation_type: str
    plate_number:   str
    fine_amount:    int
    cvcs_score:     float
    timestamp:      str
    camera_id:      str
    zone:           str
    severity:       str          # "critical" | "high" | "medium"


@dataclass
class HeatZone:
    """Aggregated zone data for heatmap layer."""
    lat:            float
    lng:            float
    intensity:      float        # 0–1 normalised violation density
    total_violations: int
    top_violation:  str
    zone_name:      str


@dataclass
class PatrolRoute:
    """Recommended patrol route from PDI engine."""
    route_id:       str
    waypoints:      List[Tuple[float, float]]   # list of (lat, lng)
    priority_zones: List[str]
    estimated_km:   float
    shift:          str          # "morning" | "afternoon" | "evening" | "night"


# ══════════════════════════════════════════════════════════════════════════════
#  1. MAPPLS TOKEN MANAGER
#  The Mappls REST APIs require an OAuth2 bearer token.
#  This class fetches and auto-refreshes the token.
# ══════════════════════════════════════════════════════════════════════════════

class MapplsTokenManager:
    """
    Fetches and caches the Mappls OAuth2 bearer token.
    Token expires in 6 hours — auto-refreshed transparently.
    """

    TOKEN_URL = "https://outpost.mappls.com/api/security/oauth/token"

    def __init__(self):
        self._token:      Optional[str]  = None
        self._expires_at: float          = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        return self._refresh()

    def _refresh(self) -> str:
        resp = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     MAPMYINDIA_CLIENT_ID,
                "client_secret": MAPMYINDIA_CLIENT_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token      = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 21600))
        return self._token

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}


# ══════════════════════════════════════════════════════════════════════════════
#  2. MAPPLS REST API CLIENT
#  Wraps Geocoding, Reverse Geocoding, Route, and Nearby APIs
# ══════════════════════════════════════════════════════════════════════════════

class MapplsAPIClient:
    """
    Thin wrapper around Mappls REST APIs used by VisionEnforce.

    All methods return parsed Python dicts / tuples.
    Raises requests.HTTPError on API failures.
    """

    BASE = "https://atlas.mappls.com/api"

    def __init__(self):
        self._tokens = MapplsTokenManager()

    # ── Geocoding: address → (lat, lng) ──────────────────────────────────────

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert a camera address / intersection name to GPS coordinates.

        Example:
            lat, lng = client.geocode("HITEC City Signal, Hyderabad")
            # → (17.4486, 78.3908)

        Use this once per camera when registering a new camera node.
        Store the result in your camera config JSON.
        """
        url    = f"{self.BASE}/places/geocode"
        params = {"address": address, "region": "IND"}
        resp   = requests.get(url, params=params,
                              headers=self._tokens.headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("copResults", {})
        if not results:
            return None
        lat = float(results.get("latitude",  0))
        lng = float(results.get("longitude", 0))
        return (lat, lng) if lat and lng else None

    # ── Reverse Geocoding: (lat, lng) → road / zone info ─────────────────────

    def reverse_geocode(self, lat: float, lng: float) -> dict:
        """
        Get road name, locality, district from GPS coordinates.

        Returns dict with keys: road, locality, district, state, pincode.
        Used to auto-populate zone names for camera profiles.
        """
        url    = f"{self.BASE}/places/geo_code/rev_geocode"
        params = {"lat": lat, "lng": lng, "region": "IND"}
        resp   = requests.get(url, params=params,
                              headers=self._tokens.headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("results", [{}])[0]
        return {
            "road":     result.get("street",   "Unknown Road"),
            "locality": result.get("subDistrict", ""),
            "district": result.get("district", ""),
            "state":    result.get("state",    ""),
            "pincode":  result.get("pincode",  ""),
        }

    # ── Nearby API: find police stations near a hotspot ───────────────────────

    def find_nearby_police(
        self,
        lat: float,
        lng: float,
        radius_m: int = 3000,
    ) -> List[dict]:
        """
        Find police stations within radius_m metres of a violation hotspot.

        Returns list of dicts: {name, lat, lng, distance_m, address}
        Used by PDI to suggest which station to dispatch from.

        Mappls keyword for police station: "police station"
        Category code: 801 (Government & Public Services)
        """
        url    = f"{self.BASE}/places/nearby/json"
        params = {
            "keywords":  "police station",
            "refLocation": f"{lat},{lng}",
            "radius":    radius_m,
            "region":    "IND",
        }
        resp = requests.get(url, params=params,
                            headers=self._tokens.headers, timeout=10)
        resp.raise_for_status()
        data    = resp.json()
        suggest = data.get("suggestedLocations", [])
        result  = []
        for s in suggest[:5]:
            result.append({
                "name":       s.get("placeName", "Police Station"),
                "lat":        float(s.get("latitude",  lat)),
                "lng":        float(s.get("longitude", lng)),
                "distance_m": int(s.get("distance", 0)),
                "address":    s.get("placeAddress", ""),
            })
        return result

    # ── Route API: build patrol route through waypoints ───────────────────────

    def get_patrol_route(
        self,
        waypoints: List[Tuple[float, float]],
    ) -> dict:
        """
        Get an optimised driving route through a list of (lat, lng) waypoints.

        Returns: {
            distance_km: float,
            duration_min: float,
            encoded_polyline: str,   ← for rendering on map
            waypoint_order: list,
        }

        The encoded polyline can be decoded with:
            import polyline
            coords = polyline.decode(encoded_polyline)
        """
        if len(waypoints) < 2:
            return {}

        origin      = f"{waypoints[0][0]},{waypoints[0][1]}"
        destination = f"{waypoints[-1][0]},{waypoints[-1][1]}"
        via         = "|".join(f"{lat},{lng}" for lat, lng in waypoints[1:-1])

        url    = f"{self.BASE}/direction/route/driving/json"
        params = {
            "origin":      origin,
            "destination": destination,
            "region":      "IND",
        }
        if via:
            params["waypoints"] = via

        resp = requests.get(url, params=params,
                            headers=self._tokens.headers, timeout=15)
        resp.raise_for_status()
        data  = resp.json()
        route = data.get("routes", [{}])[0]
        leg   = route.get("legs", [{}])[0]

        return {
            "distance_km":       round(leg.get("distance", 0) / 1000, 2),
            "duration_min":      round(leg.get("duration", 0) / 60, 1),
            "encoded_polyline":  route.get("geometry", ""),
            "waypoint_order":    list(range(len(waypoints))),
        }

    # ── Distance Matrix: police station → hotspot travel time ─────────────────

    def distance_matrix(
        self,
        origins:      List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
    ) -> List[List[dict]]:
        """
        Compute travel time and distance from each origin to each destination.

        Returns matrix[i][j] = {distance_km, duration_min}
        Use to pick the closest police station to a new hotspot.
        """
        origin_str = "|".join(f"{lat},{lng}" for lat, lng in origins)
        dest_str   = "|".join(f"{lat},{lng}" for lat, lng in destinations)

        url    = f"{self.BASE}/direction/distance_matrix/driving/json"
        params = {
            "origins":      origin_str,
            "destinations": dest_str,
            "region":       "IND",
        }
        resp = requests.get(url, params=params,
                            headers=self._tokens.headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("results", {}).get("rows", [])

        matrix = []
        for row in rows:
            cols = []
            for el in row.get("elements", []):
                cols.append({
                    "distance_km": round(el.get("distance", 0) / 1000, 2),
                    "duration_min":round(el.get("duration", 0) / 60, 1),
                })
            matrix.append(cols)
        return matrix


# ══════════════════════════════════════════════════════════════════════════════
#  3. VIOLATION MAP DATA BUILDER
#  Converts VisionEnforce challan records into map-ready data structures
# ══════════════════════════════════════════════════════════════════════════════

class ViolationMapBuilder:
    """
    Transforms raw challan records and analytics output into the data
    structures needed to drive the Mappls map frontend.

    Responsibilities:
      - Convert challan records → ViolationPin objects (individual markers)
      - Aggregate pins by zone → HeatZone objects (heatmap layer)
      - Generate PDI-driven PatrolRoute objects (route layer)
      - Produce the full JSON payload consumed by the JS frontend
    """

    # Severity thresholds based on CVCS score
    SEVERITY_MAP = {
        (0.85, 1.00): "critical",
        (0.70, 0.85): "high",
        (0.00, 0.70): "medium",
    }

    # Violation type → icon name (for Mappls custom marker icons)
    VIOLATION_ICONS = {
        "No helmet":         "helmet",
        "No seatbelt":       "seatbelt",
        "Triple riding":     "triple",
        "Red-light run":     "redlight",
        "Stop-line violation":"stopline",
        "Wrong-side driving":"wrongside",
        "Illegal parking":   "parking",
    }

    # Violation type → marker colour (hex)
    VIOLATION_COLORS = {
        "No helmet":          "#D85A30",
        "No seatbelt":        "#BA7517",
        "Triple riding":      "#7F77DD",
        "Red-light run":      "#E24B4A",
        "Stop-line violation":"#C4890A",
        "Wrong-side driving": "#991F1F",
        "Illegal parking":    "#185FA5",
    }

    def __init__(self, camera_registry: Dict[str, dict]):
        """
        camera_registry: dict mapping camera_id → {lat, lng, zone, location}
        Load from configs/cameras/*.json
        """
        self.cameras = camera_registry
        self._api    = MapplsAPIClient()

    # ── Build individual violation pins ───────────────────────────────────────

    def build_pins(self, challan_records: List[dict]) -> List[ViolationPin]:
        """
        Convert a list of challan record dicts into ViolationPin objects.
        Skips records where GPS coordinates are not available.
        """
        pins = []
        for rec in challan_records:
            cam_id = rec.get("camera_id", "")
            cam    = self.cameras.get(cam_id)
            if not cam:
                continue

            severity = self._get_severity(rec.get("cvcs_score", 0.5))
            pins.append(ViolationPin(
                challan_id     = rec["challan_id"],
                lat            = cam["lat"],
                lng            = cam["lng"],
                violation_type = rec["violation_type"],
                plate_number   = rec.get("plate_number", "UNREAD"),
                fine_amount    = rec.get("fine_amount_inr", 0),
                cvcs_score     = rec.get("cvcs_score", 0.0),
                timestamp      = rec.get("timestamp", ""),
                camera_id      = cam_id,
                zone           = cam.get("zone", "Unknown"),
                severity       = severity,
            ))
        return pins

    # ── Build heatmap zones ───────────────────────────────────────────────────

    def build_heatmap(self, pins: List[ViolationPin]) -> List[HeatZone]:
        """
        Aggregate individual pins into zone-level heatmap data.

        Clustering strategy: group pins by camera_id (each camera = one zone).
        In production: use spatial clustering (DBSCAN) for finer granularity.
        """
        from collections import defaultdict, Counter

        zone_pins: Dict[str, List[ViolationPin]] = defaultdict(list)
        for pin in pins:
            zone_pins[pin.camera_id].append(pin)

        if not zone_pins:
            return []

        max_count = max(len(v) for v in zone_pins.values())
        zones     = []

        for cam_id, vpins in zone_pins.items():
            cam       = self.cameras.get(cam_id, {})
            total     = len(vpins)
            intensity = total / max_count if max_count > 0 else 0.0
            top_type  = Counter(p.violation_type for p in vpins).most_common(1)[0][0]

            zones.append(HeatZone(
                lat              = cam.get("lat", 0.0),
                lng              = cam.get("lng", 0.0),
                intensity        = round(intensity, 3),
                total_violations = total,
                top_violation    = top_type,
                zone_name        = cam.get("zone", "Unknown"),
            ))

        return sorted(zones, key=lambda z: z.intensity, reverse=True)

    # ── Build PDI patrol routes ───────────────────────────────────────────────

    def build_patrol_routes(
        self,
        patrol_recs: List[dict],
        shift:       str = "evening",
    ) -> List[PatrolRoute]:
        """
        Convert PDI patrol recommendations into route objects.
        Groups top priority zones into patrol beats and calls Route API.

        patrol_recs: output from AnalyticsEngine.patrol_recommendations()
        shift:       "morning" | "afternoon" | "evening" | "night"
        """
        # Pick top 5 zones for this shift
        top_zones = [r for r in patrol_recs
                     if r.get("priority") in ("critical", "high")][:5]
        if len(top_zones) < 2:
            return []

        waypoints = []
        zone_names = []
        for rec in top_zones:
            zone = rec.get("zone", "")
            cam  = self._find_camera_by_zone(zone)
            if cam:
                waypoints.append((cam["lat"], cam["lng"]))
                zone_names.append(zone)

        if len(waypoints) < 2:
            return []

        try:
            route_data = self._api.get_patrol_route(waypoints)
        except Exception as e:
            print(f"Route API error: {e}")
            route_data = {"distance_km": 0, "duration_min": 0, "encoded_polyline": ""}

        return [PatrolRoute(
            route_id       = f"PATROL-{shift.upper()}-{datetime.utcnow().strftime('%H%M')}",
            waypoints      = waypoints,
            priority_zones = zone_names,
            estimated_km   = route_data.get("distance_km", 0),
            shift          = shift,
        )]

    # ── Build complete map JSON payload ───────────────────────────────────────

    def build_map_payload(
        self,
        challan_records: List[dict],
        patrol_recs:     List[dict],
        shift:           str = "evening",
    ) -> dict:
        """
        Master function: builds the complete JSON payload that the
        Mappls JS frontend (map_dashboard.html) reads via /api/map-data.

        Returns:
        {
          "pins":     [...],       ← individual violation markers
          "heatmap":  [...],       ← zone-level intensity circles
          "routes":   [...],       ← patrol beat polylines
          "summary":  {...},       ← counts for the info panel
          "timestamp": "...",
        }
        """
        pins    = self.build_pins(challan_records)
        heatmap = self.build_heatmap(pins)
        routes  = self.build_patrol_routes(patrol_recs, shift)

        from collections import Counter
        vtype_counts = Counter(p.violation_type for p in pins)
        severity_counts = Counter(p.severity for p in pins)

        return {
            "pins":    [asdict(p) for p in pins],
            "heatmap": [asdict(h) for h in heatmap],
            "routes":  [
                {
                    "route_id":      r.route_id,
                    "waypoints":     r.waypoints,
                    "priority_zones":r.priority_zones,
                    "estimated_km":  r.estimated_km,
                    "shift":         r.shift,
                }
                for r in routes
            ],
            "summary": {
                "total_violations": len(pins),
                "by_type":          dict(vtype_counts.most_common()),
                "by_severity":      dict(severity_counts),
                "top_zone":         heatmap[0].zone_name if heatmap else "N/A",
                "top_violation":    vtype_counts.most_common(1)[0][0] if vtype_counts else "N/A",
            },
            "violation_colors": self.VIOLATION_COLORS,
            "timestamp":         datetime.utcnow().isoformat() + "Z",
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_severity(self, cvcs_score: float) -> str:
        for (low, high), label in self.SEVERITY_MAP.items():
            if low <= cvcs_score <= high:
                return label
        return "medium"

    def _find_camera_by_zone(self, zone_name: str) -> Optional[dict]:
        for cam in self.cameras.values():
            if cam.get("zone") == zone_name:
                return cam
        return None