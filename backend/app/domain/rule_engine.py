# rule_engine.py — Logic-based violation detection
#
# Handles violations that don't need trained vision models:
#   1. Stop-line violation  — vehicle centroid crosses calibrated line
#   2. Red-light violation  — signal state detection + vehicle in motion
#   3. Wrong-side driving   — vehicle direction vector vs lane boundary
#   4. Illegal parking      — stationary vehicle in no-parking zone over time
#


import cv2
import numpy as np
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from collections import deque, defaultdict


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class RuleViolation:
    """Violation detected by a rule (not a trained model)."""
    violation_type: str
    confidence:     float          # rule-based confidence (0–1)
    bbox:           Tuple[int, int, int, int]
    evidence:       dict = field(default_factory=dict)  # supporting data


# ══════════════════════════════════════════════════════════════════════════════
#  1. STOP-LINE VIOLATION DETECTOR
#  Logic: vehicle centroid crosses a calibrated horizontal line
#         while the signal state is red or unknown.
# ══════════════════════════════════════════════════════════════════════════════

class StopLineDetector:
    """
    Detects vehicles that cross the stop line at an intersection.

    Setup (one-time per camera):
        detector = StopLineDetector()
        detector.calibrate(frame)   ← click on the stop line in the frame
                                      OR pass y_pixel directly

    Runtime:
        violations = detector.check(vehicle_bboxes, frame_height)

    How it works:
        - Stop line = a horizontal line at pixel y = stop_line_y
        - A vehicle violates if its BOTTOM edge (bbox y2) > stop_line_y
          (i.e. the vehicle has crossed into the intersection zone)
        - Confidence scales with how far past the line the vehicle is
    """

    def __init__(self, stop_line_y: Optional[int] = None):
        self.stop_line_y  = stop_line_y
        self.margin_px    = 10     # pixels of tolerance before flagging
        self.violation_zone_depth = 80   # pixels — how deep past line counts

    def calibrate(self, frame: np.ndarray) -> int:
        """
        Interactive calibration: draws frame and lets user click stop line.
        Returns the y-pixel of the stop line.

        In production: store calibration per camera_id in a JSON config file.
        """
        y_values = []

        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                y_values.append(y)
                print(f"Stop line set at y={y}")
                cv2.destroyAllWindows()

        cv2.imshow("Click on stop line", frame)
        cv2.setMouseCallback("Click on stop line", mouse_callback)
        cv2.waitKey(0)

        if y_values:
            self.stop_line_y = y_values[0]
        return self.stop_line_y

    def set_line(self, y_pixel: int):
        """Programmatically set the stop line (from saved calibration)."""
        self.stop_line_y = y_pixel

    def check(
        self,
        vehicle_bboxes: List[Tuple[int, int, int, int]],
        signal_state:   str = "red",       # "red" | "green" | "unknown"
    ) -> List[RuleViolation]:
        """
        Check all vehicle bounding boxes against the stop line.

        Args:
            vehicle_bboxes : list of (x1, y1, x2, y2) for each vehicle
            signal_state   : current traffic signal state

        Returns:
            list of RuleViolation for vehicles that crossed the line
        """
        if self.stop_line_y is None:
            return []

        # Stop-line violations only matter when signal is red or unknown
        if signal_state == "green":
            return []

        violations = []
        for bbox in vehicle_bboxes:
            x1, y1, x2, y2 = bbox
            vehicle_bottom = y2           # bottom edge of vehicle bbox

            if vehicle_bottom > (self.stop_line_y + self.margin_px):
                # How far past the line (scales confidence)
                depth = vehicle_bottom - self.stop_line_y
                conf  = min(0.95, 0.65 + (depth / self.violation_zone_depth) * 0.30)

                violations.append(RuleViolation(
                    violation_type = "Stop-line violation",
                    confidence     = round(conf, 3),
                    bbox           = bbox,
                    evidence       = {
                        "stop_line_y":    self.stop_line_y,
                        "vehicle_bottom": vehicle_bottom,
                        "depth_px":       depth,
                        "signal_state":   signal_state,
                    }
                ))
        return violations

    def draw_line(self, frame: np.ndarray) -> np.ndarray:
        """Draw the calibrated stop line on a frame for visualisation."""
        if self.stop_line_y is None:
            return frame
        h, w = frame.shape[:2]
        cv2.line(frame, (0, self.stop_line_y), (w, self.stop_line_y),
                 (0, 255, 255), 2)
        cv2.putText(frame, "STOP LINE", (10, self.stop_line_y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        return frame


# ══════════════════════════════════════════════════════════════════════════════
#  2. RED-LIGHT VIOLATION DETECTOR
#  Logic: signal is RED + vehicle is moving past stop line
# ══════════════════════════════════════════════════════════════════════════════

class RedLightDetector:
    """
    Detects red-light running violations.

    Two components:
      A) Signal state detector — reads the traffic light colour from a
         defined Region of Interest (ROI) in the frame.
      B) Vehicle motion check — vehicle is moving (not just stopped past line).

    Signal ROI setup:
        detector = RedLightDetector()
        detector.set_signal_roi(x1, y1, x2, y2)
        # This is the bounding box of the traffic light in the camera view.
        # Calibrate once per camera and save to config.

    How colour detection works:
        - Crop the signal ROI
        - Convert to HSV colour space
        - Apply colour masks for red / green / amber
        - The dominant colour = signal state
        - Red in HSV wraps around (0° and 360°), so two masks are needed.
    """

    # HSV colour ranges for Indian traffic signals
    # (tune these if your camera has different white balance)
    RED_LOWER_1  = np.array([0,   120, 70])
    RED_UPPER_1  = np.array([10,  255, 255])
    RED_LOWER_2  = np.array([170, 120, 70])
    RED_UPPER_2  = np.array([180, 255, 255])
    GREEN_LOWER  = np.array([40,  100, 70])
    GREEN_UPPER  = np.array([90,  255, 255])
    AMBER_LOWER  = np.array([15,  150, 70])
    AMBER_UPPER  = np.array([35,  255, 255])

    def __init__(self):
        self.signal_roi    = None     # (x1, y1, x2, y2) of traffic light
        self.stop_line_y   = None
        self._prev_frames: deque = deque(maxlen=5)
        self._state_history: deque = deque(maxlen=10)

    def set_signal_roi(self, x1: int, y1: int, x2: int, y2: int):
        self.signal_roi = (x1, y1, x2, y2)

    def set_stop_line(self, y_pixel: int):
        self.stop_line_y = y_pixel

    def detect_signal_state(self, frame: np.ndarray) -> str:
        """
        Returns "red", "green", "amber", or "unknown".
        Uses the most common state over the last 10 frames for stability
        (avoids false positives from brief lighting flicker).
        """
        if self.signal_roi is None:
            return "unknown"

        x1, y1, x2, y2 = self.signal_roi
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return "unknown"

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        red_mask  = (cv2.inRange(hsv, self.RED_LOWER_1, self.RED_UPPER_1) |
                     cv2.inRange(hsv, self.RED_LOWER_2, self.RED_UPPER_2))
        green_mask = cv2.inRange(hsv, self.GREEN_LOWER, self.GREEN_UPPER)
        amber_mask = cv2.inRange(hsv, self.AMBER_LOWER, self.AMBER_UPPER)

        counts = {
            "red":   int(np.sum(red_mask   > 0)),
            "green": int(np.sum(green_mask > 0)),
            "amber": int(np.sum(amber_mask > 0)),
        }
        total = roi.shape[0] * roi.shape[1]
        threshold = total * 0.08   # at least 8% of ROI must be the colour

        state = "unknown"
        best  = max(counts.values())
        if best >= threshold:
            state = max(counts, key=counts.get)

        self._state_history.append(state)
        # Return majority vote over last 10 frames
        from collections import Counter
        votes = Counter(self._state_history)
        return votes.most_common(1)[0][0]

    def check(
        self,
        frame:          np.ndarray,
        vehicle_bboxes: List[Tuple[int, int, int, int]],
        prev_bboxes:    List[Tuple[int, int, int, int]],  # from previous frame
    ) -> Tuple[str, List[RuleViolation]]:
        """
        Full red-light violation check.

        Args:
            frame          : current frame
            vehicle_bboxes : vehicle detections in current frame
            prev_bboxes    : vehicle detections in previous frame

        Returns:
            (signal_state, list_of_violations)
        """
        signal = self.detect_signal_state(frame)
        if signal != "red" or self.stop_line_y is None:
            return signal, []

        violations = []
        for bbox in vehicle_bboxes:
            x1, y1, x2, y2 = bbox
            vehicle_bottom = y2

            # Vehicle must be past the stop line
            if vehicle_bottom <= self.stop_line_y:
                continue

            # Vehicle must be moving (compare centroid to previous frame)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            is_moving = self._is_moving(cx, cy, prev_bboxes)

            if is_moving:
                violations.append(RuleViolation(
                    violation_type = "Red-light run",
                    confidence     = 0.88,
                    bbox           = bbox,
                    evidence       = {
                        "signal_state": signal,
                        "vehicle_past_line": True,
                        "vehicle_moving":    True,
                    }
                ))
        return signal, violations

    @staticmethod
    def _is_moving(
        cx: int,
        cy: int,
        prev_bboxes: List[Tuple[int, int, int, int]],
        threshold: int = 8,
    ) -> bool:
        """
        True if the vehicle centroid has moved more than `threshold` pixels
        from its closest match in the previous frame.
        """
        if not prev_bboxes:
            return True  # no previous frame → assume moving
        min_dist = float("inf")
        for pb in prev_bboxes:
            px = (pb[0] + pb[2]) // 2
            py = (pb[1] + pb[3]) // 2
            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            min_dist = min(min_dist, dist)
        return min_dist > threshold


# ══════════════════════════════════════════════════════════════════════════════
#  3. WRONG-SIDE DRIVING DETECTOR
#  Logic: vehicle direction vector opposes expected lane direction
# ══════════════════════════════════════════════════════════════════════════════

class WrongSideDetector:
    """
    Detects vehicles driving on the wrong side of the road.

    How it works:
      1. Track each vehicle centroid across N frames using a simple
         nearest-neighbour tracker.
      2. Compute the vehicle's direction vector (dx, dy) over the track.
      3. Compare to the expected flow direction for each lane half.

    Camera calibration required:
        - lane_boundary_x: x-pixel that divides the two carriageway lanes
        - expected_direction: for each side, is the vehicle expected to
          move left→right (+dx) or right→left (-dx)?

    Example for a typical Indian two-lane road camera:
        Left half  (x < boundary): vehicles should move left-to-right (+dx)
        Right half (x > boundary): vehicles should move right-to-left (-dx)
        A vehicle in the left half moving with strong -dx is wrong-side.
    """

    def __init__(
        self,
        lane_boundary_x:    int    = None,
        expected_left_dx:   float  = 1.0,    # +1 = left→right, -1 = right→left
        track_window:       int    = 8,       # frames to track before deciding
        min_motion_px:      float  = 5.0,     # ignore near-stationary vehicles
        confidence_base:    float  = 0.80,
    ):
        self.lane_boundary_x  = lane_boundary_x
        self.expected_left_dx = expected_left_dx
        self.track_window     = track_window
        self.min_motion_px    = min_motion_px
        self.confidence_base  = confidence_base

        # vehicle_id → deque of (cx, cy) centroids
        self._tracks: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=track_window)
        )
        self._next_id = 0
        self._bbox_to_id: Dict[Tuple, int] = {}

    def set_lane_boundary(self, x_pixel: int, expected_left_dx: float = 1.0):
        self.lane_boundary_x  = x_pixel
        self.expected_left_dx = expected_left_dx

    def update_and_check(
        self,
        vehicle_bboxes: List[Tuple[int, int, int, int]],
    ) -> List[RuleViolation]:
        """
        Feed current-frame detections, update tracks, return violations.
        Call once per frame in sequence.
        """
        if self.lane_boundary_x is None:
            return []

        self._update_tracks(vehicle_bboxes)
        violations = []

        for vid, track in self._tracks.items():
            if len(track) < self.track_window // 2:
                continue    # not enough history yet

            # Compute overall direction vector
            dx = track[-1][0] - track[0][0]
            dy = track[-1][1] - track[0][1]
            total_motion = (dx**2 + dy**2) ** 0.5

            if total_motion < self.min_motion_px:
                continue    # vehicle is effectively stationary

            # Current centroid x position
            cx = track[-1][0]
            cy = track[-1][1]

            # Determine expected dx sign for this lane half
            if cx < self.lane_boundary_x:
                expected_sign = np.sign(self.expected_left_dx)
            else:
                expected_sign = -np.sign(self.expected_left_dx)

            actual_sign = np.sign(dx)

            if actual_sign != expected_sign and abs(dx) > self.min_motion_px:
                # Scale confidence by how strongly wrong-side the motion is
                wrongness = min(1.0, abs(dx) / 30.0)
                conf = self.confidence_base + wrongness * 0.10

                # Reconstruct bbox from last known position (approximate)
                bbox = self._id_to_bbox(vid, vehicle_bboxes)
                if bbox:
                    violations.append(RuleViolation(
                        violation_type = "Wrong-side driving",
                        confidence     = round(min(conf, 0.95), 3),
                        bbox           = bbox,
                        evidence       = {
                            "dx":             round(dx, 1),
                            "expected_sign":  int(expected_sign),
                            "actual_sign":    int(actual_sign),
                            "lane_half":      "left" if cx < self.lane_boundary_x else "right",
                            "track_length":   len(track),
                        }
                    ))
        return violations

    def _update_tracks(self, bboxes: List[Tuple]):
        """
        Nearest-neighbour tracker: assign each bbox to the closest
        existing track, or create a new track if no close match.
        """
        centroids = [((b[0]+b[2])//2, (b[1]+b[3])//2) for b in bboxes]
        new_bbox_to_id = {}

        for i, (cx, cy) in enumerate(centroids):
            best_id   = None
            best_dist = 50.0    # max px distance to match a track

            for vid, track in self._tracks.items():
                if not track:
                    continue
                px, py = track[-1]
                dist = ((cx-px)**2 + (cy-py)**2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_id   = vid

            if best_id is None:
                best_id = self._next_id
                self._next_id += 1

            self._tracks[best_id].append((cx, cy))
            new_bbox_to_id[bboxes[i]] = best_id

        self._bbox_to_id = new_bbox_to_id

    def _id_to_bbox(self, vid: int, bboxes: List[Tuple]) -> Optional[Tuple]:
        for bbox, bid in self._bbox_to_id.items():
            if bid == vid:
                return bbox
        return bboxes[0] if bboxes else None


# ══════════════════════════════════════════════════════════════════════════════
#  4. ILLEGAL PARKING DETECTOR
#  Logic: vehicle remains stationary in a restricted zone for > N seconds
# ══════════════════════════════════════════════════════════════════════════════

class IllegalParkingDetector:
    """
    Detects vehicles illegally parked in no-parking zones.

    How it works:
      1. Define no-parking zones as polygons in image coordinates.
         (Calibrated once per camera from the camera view.)
      2. Track each vehicle's position across frames.
      3. If a vehicle's centroid is inside a no-parking polygon AND
         it has not moved more than `stationary_threshold` pixels for
         longer than `max_stationary_seconds`, flag it.

    No-parking zone definition:
        Polygon vertices in image coordinates.
        Example: a yellow box zone in front of a hospital entrance.
        Zones are stored in camera config JSON and loaded at startup.
    """

    def __init__(
        self,
        no_parking_zones:       List[np.ndarray] = None,  # list of polygons
        max_stationary_seconds: float = 30.0,
        stationary_threshold:   float = 15.0,   # pixels of allowed movement
        fps:                    float = 25.0,
    ):
        self.zones                  = no_parking_zones or []
        self.max_stationary_frames  = int(max_stationary_seconds * fps)
        self.stationary_threshold   = stationary_threshold

        # vehicle_id → {"bbox": ..., "first_seen_frame": ..., "last_cx": ..., "last_cy": ...}
        self._parked_vehicles: Dict[int, dict] = {}
        self._frame_count = 0
        self._next_id     = 0
        self._active_ids: Dict[Tuple, int] = {}

    def add_no_parking_zone(self, polygon_points: List[Tuple[int, int]]):
        """
        Add a no-parking zone polygon.

        polygon_points: list of (x, y) vertices in image coordinates.
        Example:
            detector.add_no_parking_zone([(100, 200), (300, 200),
                                          (300, 350), (100, 350)])
        """
        self.zones.append(np.array(polygon_points, dtype=np.int32))

    def update_and_check(
        self,
        vehicle_bboxes: List[Tuple[int, int, int, int]],
    ) -> List[RuleViolation]:
        """
        Update vehicle tracking and return parking violations.
        Must be called once per frame in sequence.
        """
        self._frame_count += 1
        if not self.zones:
            return []

        violations = []
        new_active: Dict[Tuple, int] = {}

        for bbox in vehicle_bboxes:
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2

            # Match to existing tracked vehicle
            vid = self._match_vehicle(cx, cy)

            if vid in self._parked_vehicles:
                entry   = self._parked_vehicles[vid]
                moved   = ((cx - entry["last_cx"])**2 +
                           (cy - entry["last_cy"])**2) ** 0.5
                if moved > self.stationary_threshold:
                    # Vehicle moved — reset timer
                    entry["first_seen_frame"] = self._frame_count
                    entry["last_cx"] = cx
                    entry["last_cy"] = cy
                else:
                    # Still stationary — check duration
                    frames_stationary = self._frame_count - entry["first_seen_frame"]
                    if (frames_stationary >= self.max_stationary_frames and
                            self._in_no_parking_zone(cx, cy)):
                        conf = min(0.92, 0.70 + frames_stationary /
                                   (self.max_stationary_frames * 3) * 0.22)
                        violations.append(RuleViolation(
                            violation_type = "Illegal parking",
                            confidence     = round(conf, 3),
                            bbox           = bbox,
                            evidence       = {
                                "stationary_seconds": round(
                                    frames_stationary / max(self._frame_count, 1) * 30, 1
                                ),
                                "zone_centroid": (cx, cy),
                            }
                        ))
            else:
                self._parked_vehicles[vid] = {
                    "bbox":              bbox,
                    "first_seen_frame":  self._frame_count,
                    "last_cx":           cx,
                    "last_cy":           cy,
                }
            new_active[bbox] = vid

        self._active_ids = new_active
        return violations

    def _in_no_parking_zone(self, cx: int, cy: int) -> bool:
        """Returns True if point (cx, cy) is inside any no-parking polygon."""
        for zone in self.zones:
            if cv2.pointPolygonTest(zone, (float(cx), float(cy)), False) >= 0:
                return True
        return False

    def _match_vehicle(self, cx: int, cy: int) -> int:
        """Match centroid to nearest tracked vehicle or create new entry."""
        best_id   = None
        best_dist = 60.0
        for bbox, vid in self._active_ids.items():
            px = (bbox[0] + bbox[2]) // 2
            py = (bbox[1] + bbox[3]) // 2
            dist = ((cx-px)**2 + (cy-py)**2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id   = vid
        if best_id is None:
            best_id = self._next_id
            self._next_id += 1
        return best_id

    def draw_zones(self, frame: np.ndarray) -> np.ndarray:
        """Overlay no-parking zones on frame for visualisation."""
        overlay = frame.copy()
        for zone in self.zones:
            cv2.fillPoly(overlay, [zone], (0, 0, 180))
            cv2.polylines(frame, [zone], True, (0, 0, 255), 2)
            x, y = zone[0]
            cv2.putText(frame, "NO PARKING", (int(x), int(y) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        return cv2.addWeighted(overlay, 0.20, frame, 0.80, 0)