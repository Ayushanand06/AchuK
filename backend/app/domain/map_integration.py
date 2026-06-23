
import json
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

try:
    from app.config import (
        MAPMYINDIA_API_KEY,
        MAPMYINDIA_CLIENT_ID,
        MAPMYINDIA_CLIENT_SECRET,
    )
except ImportError:
    MAPMYINDIA_API_KEY      = "YOUR_API_KEY_HERE"
    MAPMYINDIA_CLIENT_ID    = "YOUR_CLIENT_ID_HERE"
    MAPMYINDIA_CLIENT_SECRET= "YOUR_CLIENT_SECRET_HERE"



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
    severity:       str


@dataclass
class HeatZone:
    """Aggregated zone data for heatmap layer."""
    lat:            float
    lng:            float
    intensity:      float
    total_violations: int
    top_violation:  str
    zone_name:      str


@dataclass
class PatrolRoute:
    """Recommended patrol route from PDI engine."""
    route_id:       str
    waypoints:      List[Tuple[float, float]]
    priority_zones: List[str]
    estimated_km:   float
    shift:          str



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



class MapplsAPIClient:
    """
    Thin wrapper around Mappls REST APIs using a single **static REST key**
    (the key goes in the URL path, no OAuth token needed):

        https://apis.mappls.com/advancedmaps/v1/{KEY}/<endpoint>

    All methods return parsed Python dicts / tuples and raise
    requests.HTTPError on API failures. Note: Mappls coordinate order for
    routing endpoints is lng,lat.
    """

    BASE = "https://apis.mappls.com/advancedmaps/v1"

    def __init__(self):
        self._key = MAPMYINDIA_API_KEY

    def _url(self, path: str) -> str:
        return f"{self.BASE}/{self._key}/{path}"

    # ── Geocoding: address → (lat, lng) ──────────────────────────────────────

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert a camera address / intersection name to GPS coordinates.

            lat, lng = client.geocode("HITEC City Signal, Hyderabad")
        """
        resp = requests.get(self._url("geo_code"),
                            params={"addr": address, "region": "IND"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or data.get("copResults")
        if isinstance(results, list):
            results = results[0] if results else None
        if not results:
            return None
        lat = float(results.get("latitude", results.get("lat", 0)) or 0)
        lng = float(results.get("longitude", results.get("lng", 0)) or 0)
        return (lat, lng) if lat and lng else None


    def reverse_geocode(self, lat: float, lng: float) -> dict:
        """Road / locality / district from GPS coordinates."""
        resp = requests.get(self._url("rev_geocode"),
                            params={"lat": lat, "lng": lng, "region": "IND"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = (data.get("results") or [{}])[0]
        return {
            "road":     result.get("street", result.get("formatted_address", "Unknown Road")),
            "locality": result.get("subDistrict", result.get("locality", "")),
            "district": result.get("district", ""),
            "state":    result.get("state", ""),
            "pincode":  result.get("pincode", ""),
        }


    def find_nearby_police(
        self,
        lat: float,
        lng: float,
        radius_m: int = 3000,
    ) -> List[dict]:
        """Find police stations within radius_m metres → list of dicts."""
        resp = requests.get(
            self._url("nearby"),
            params={
                "keywords": "police_station",
                "refLocation": f"{lat},{lng}",
                "radius": radius_m,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        suggest = data.get("suggestedLocations", []) or data.get("results", [])
        out = []
        for s in suggest[:5]:
            out.append({
                "name":       s.get("placeName", s.get("poi", "Police Station")),
                "lat":        float(s.get("latitude", s.get("lat", lat)) or lat),
                "lng":        float(s.get("longitude", s.get("lng", lng)) or lng),
                "distance_m": int(s.get("distance", 0) or 0),
                "address":    s.get("placeAddress", s.get("address", "")),
            })
        return out


    def get_patrol_route(
        self,
        waypoints: List[Tuple[float, float]],
    ) -> dict:
        """
        Driving route through (lat, lng) waypoints via the Route ADV API.
        Returns {distance_km, duration_min, encoded_polyline, waypoint_order}.
        Mappls coordinate order is lng,lat, so we flip here.
        """
        if len(waypoints) < 2:
            return {}

        coords = ";".join(f"{lng},{lat}" for lat, lng in waypoints)
        resp = requests.get(
            self._url(f"route_adv/driving/{coords}"),
            params={"geometries": "polyline", "overview": "full"},
            timeout=15,
        )
        resp.raise_for_status()
        route = (resp.json().get("routes") or [{}])[0]
        return {
            "distance_km":      round(route.get("distance", 0) / 1000, 2),
            "duration_min":     round(route.get("duration", 0) / 60, 1),
            "encoded_polyline": route.get("geometry", ""),
            "waypoint_order":   list(range(len(waypoints))),
        }


    def distance_matrix(
        self,
        origins:      List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
    ) -> List[List[dict]]:
        """
        Travel time/distance from each origin to each destination.
        matrix[i][j] = {distance_km, duration_min}. Coordinate order is lng,lat.
        """
        all_pts = list(origins) + list(destinations)
        coords  = ";".join(f"{lng},{lat}" for lat, lng in all_pts)
        srcs    = ";".join(str(i) for i in range(len(origins)))
        dests   = ";".join(str(i + len(origins)) for i in range(len(destinations)))

        resp = requests.get(
            self._url(f"distance_matrix/driving/{coords}"),
            params={"sources": srcs, "destinations": dests},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        dist_rows = data.get("results", {}).get("distances", [])
        dur_rows  = data.get("results", {}).get("durations", [])

        matrix = []
        for i in range(len(dist_rows)):
            cols = []
            for j in range(len(dist_rows[i])):
                cols.append({
                    "distance_km":  round((dist_rows[i][j] or 0) / 1000, 2),
                    "duration_min": round((dur_rows[i][j] or 0) / 60, 1) if dur_rows else 0,
                })
            matrix.append(cols)
        return matrix



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

    SEVERITY_MAP = {
        (0.85, 1.00): "critical",
        (0.70, 0.85): "high",
        (0.00, 0.70): "medium",
    }

    VIOLATION_ICONS = {
        "No helmet":         "helmet",
        "No seatbelt":       "seatbelt",
        "Triple riding":     "triple",
        "Red-light run":     "redlight",
        "Stop-line violation":"stopline",
        "Wrong-side driving":"wrongside",
        "Illegal parking":   "parking",
    }

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