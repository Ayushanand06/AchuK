# config.py — central configuration for the traffic-violation backend
#
# Values that come from the environment (model paths, Mappls keys, output dir)
# are sourced from app.settings. Everything else is a tunable constant.

import re
from app.settings import settings

# ─── Model weight paths (4 separate single-purpose YOLOv8 models) ──────────────
HELMET_MODEL       = settings.helmet_model_path
SEATBELT_MODEL     = settings.seatbelt_model_path
TRIPLE_MODEL       = settings.triple_model_path
PLATE_DETECT_MODEL = settings.plate_model_path

# ─── Mappls / MapMyIndia credentials (consumed by map_integration.py) ──────────
MAPMYINDIA_API_KEY       = settings.mapmyindia_api_key
MAPMYINDIA_CLIENT_ID     = settings.mapmyindia_client_id
MAPMYINDIA_CLIENT_SECRET = settings.mapmyindia_client_secret

# ─── Reference class names (per-model .names are read dynamically at load) ──────
# Kept for documentation; the MultiModelDetector resolves each model's own labels.
CLASS_NAMES = {
    0:  "person",        1:  "bicycle",     2:  "motorcycle",  3:  "car",
    4:  "bus",           5:  "truck",       6:  "helmet",      7:  "no_helmet",
    8:  "seatbelt",      9:  "no_seatbelt", 10: "license_plate",11: "triple_riding",
    12: "stop_line",     13: "red_light",   14: "green_light", 15: "wrong_side",
}

# ─── Per-model violation mapping ───────────────────────────────────────────────
# For each model, map a (lower-cased) substring of the model's class label to a
# canonical violation label. Resolved against each model's real `.names` at
# runtime, so it tolerates whatever exact class strings the weights were trained
# with. Anything not matched here is treated as a non-violation context object
# (rider, helmet present, motorcycle, etc.).
MODEL_VIOLATION_MAP = {
    "helmet": {
        "no_helmet":       "No helmet",
        "no-helmet":       "No helmet",
        "nohelmet":        "No helmet",
        "without_helmet":  "No helmet",
        "without helmet":  "No helmet",
        "helmetless":      "No helmet",
        "head":            "No helmet",   # some datasets mark a bare head
    },
    "seatbelt": {
        "no_seatbelt":     "No seatbelt",
        "no-seatbelt":     "No seatbelt",
        "noseatbelt":      "No seatbelt",
        "without_seatbelt":"No seatbelt",
        "no_belt":         "No seatbelt",
        "without_belt":    "No seatbelt",
    },
    "triple": {
        "triple":          "Triple riding",
        "tripple":         "Triple riding",  # frequent dataset misspelling
        "triple_riding":   "Triple riding",
        "triples":         "Triple riding",
        "overload":        "Triple riding",
    },
}

# Class-name substrings that identify two-wheelers / riders (triple-riding fallback)
MOTORCYCLE_KEYWORDS = ("motorcycle", "motorbike", "bike", "scooter", "two_wheeler", "twowheeler")
PERSON_KEYWORDS     = ("person", "rider", "people", "passenger", "motorcyclist", "head")

# COCO class IDs the general vehicle detector treats as "vehicles" for the rule
# engines (car, motorcycle, bus, truck). Used by the video pipeline only.
VEHICLE_CLASS_IDS = {2, 3, 5, 7}

# Cooldown (seconds) before the same ongoing violation can issue another challan.
DEDUP_COOLDOWN_SEC = settings.dedup_cooldown_sec
VIDEO_SKIP_FRAMES  = settings.video_skip_frames

# ─── Detection thresholds ──────────────────────────────────────────────────────
YOLO_CONF_THRESHOLD   = settings.yolo_conf_threshold
YOLO_IOU_THRESHOLD    = settings.yolo_iou_threshold
CVCS_AUTO_THRESHOLD   = 0.80   # CVCS score above this → auto challan
CVCS_REVIEW_THRESHOLD = 0.55   # between this and auto → human review; below → discard

# ─── OCR settings ─────────────────────────────────────────────────────────────
OCR_UPSCALE_FACTOR    = 4      # upscale plate crop before OCR
OCR_MIN_CONFIDENCE    = 0.60   # minimum mean character confidence
PLATE_ASPECT_MIN      = 2.0    # min width/height ratio of a valid plate crop
PLATE_ASPECT_MAX      = 6.0    # max width/height ratio

# Indian number plate regex: e.g. MH12AB1234, TS09EF4421
PLATE_REGEX = re.compile(
    r"^[A-Z]{2}[\s-]?[0-9]{1,2}[\s-]?[A-Z]{1,2}[\s-]?[0-9]{4}$"
)

# ─── Image preprocessing ──────────────────────────────────────────────────────
CLAHE_CLIP_LIMIT      = 2.0
CLAHE_TILE_GRID       = (8, 8)
FRAME_BUFFER_SIZE     = 5      # frames averaged for motion-blur reduction (video)
TARGET_WIDTH          = 1280   # resize input to this width before inference

# ─── CVCS contextual weights ──────────────────────────────────────────────────
CVCS_WEIGHTS = {
    "model_conf":      0.40,
    "resolution":      0.20,
    "lighting":        0.15,
    "vehicle_speed":   0.10,
    "camera_history":  0.15,
}

# ─── Evidence & storage ───────────────────────────────────────────────────────
OUTPUT_DIR             = settings.output_dir
EVIDENCE_IMAGE_QUALITY = 95
HASH_ALGORITHM         = "sha256"

# ─── Fine amounts (INR) — Motor Vehicles Act 2019 ─────────────────────────────
FINE_AMOUNTS = {
    "No helmet":           1000,
    "No seatbelt":         1000,
    "Triple riding":       1000,
    "Red-light run":       5000,
    "Wrong-side driving":  5000,
    "Stop-line violation": 500,
    "Illegal parking":     500,
}

# ─── Camera metadata defaults ─────────────────────────────────────────────────
CAMERA_DEFAULTS = {
    "resolution":    "1080p",
    "fps":           30,
    "location":      "Unknown",
    "zone":          "General",
    "historical_fp": 0.05,
}
