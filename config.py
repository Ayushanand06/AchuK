# config.py — Achuk central configuration

# ─── Model paths ───────────────────────────────────────────────────────────────


# ─── Detection class IDs (match your dataset labels exactly) ──────────────────
CLASS_NAMES = {
    0:  "person",
    1:  "bicycle",
    2:  "motorcycle",
    3:  "car",
    4:  "bus",
    5:  "truck",
    6:  "helmet",
    7:  "no_helmet",
    8:  "seatbelt",
    9:  "no_seatbelt",
    10: "license_plate",
    11: "triple_riding",
    12: "stop_line",
    13: "red_light",
    14: "green_light",
    15: "wrong_side",
}

VIOLATION_CLASSES = {7, 9, 11, 13, 15}      # class IDs that are violations
VIOLATION_LABELS = {
    7:  "No helmet",
    9:  "No seatbelt",
    11: "Triple riding",
    13: "Red-light run",
    15: "Wrong-side driving",
}

# ─── Detection thresholds ──────────────────────────────────────────────────────
YOLO_CONF_THRESHOLD   = 0.45   # minimum raw confidence from YOLO
YOLO_IOU_THRESHOLD    = 0.45   # NMS IoU threshold
CVCS_AUTO_THRESHOLD   = 0.80   # CVCS score above this → auto challan
CVCS_REVIEW_THRESHOLD = 0.55   # CVCS score between this and auto → human review
                                # below review threshold → discard

# ─── OCR settings ─────────────────────────────────────────────────────────────
OCR_UPSCALE_FACTOR    = 4      # Real-ESRGAN upscale before OCR
OCR_MIN_CONFIDENCE    = 0.60   # minimum PaddleOCR character confidence
PLATE_ASPECT_MIN      = 2.0    # min width/height ratio of a valid plate crop
PLATE_ASPECT_MAX      = 6.0    # max width/height ratio

# Indian number plate regex: e.g. MH12AB1234, TS09EF4421
import re
PLATE_REGEX = re.compile(
    r"^[A-Z]{2}[\s-]?[0-9]{1,2}[\s-]?[A-Z]{1,2}[\s-]?[0-9]{4}$"
)

# ─── Image preprocessing ──────────────────────────────────────────────────────
CLAHE_CLIP_LIMIT      = 2.0
CLAHE_TILE_GRID       = (8, 8)
FRAME_BUFFER_SIZE     = 5      # frames averaged for motion-blur reduction
TARGET_WIDTH          = 1280   # resize input to this width before inference

# ─── CVCS contextual weights ──────────────────────────────────────────────────
# Each factor contributes a multiplier to the base model confidence
CVCS_WEIGHTS = {
    "model_conf":      0.40,   # raw YOLO confidence
    "resolution":      0.20,   # image resolution quality
    "lighting":        0.15,   # estimated lighting score
    "vehicle_speed":   0.10,   # slower = cleaner OCR
    "camera_history":  0.15,   # historical FP rate of this camera node
}

# ─── Evidence & storage ───────────────────────────────────────────────────────
OUTPUT_DIR            = "output/challans"
EVIDENCE_IMAGE_QUALITY = 95    # JPEG quality for annotated evidence image
HASH_ALGORITHM        = "sha256"

# ─── Fine amounts (INR) matching Motor Vehicles Act 2019 ─────────────────────
FINE_AMOUNTS = {
    "No helmet":           1000,
    "No seatbelt":         1000,
    "Triple riding":       1000,
    "Red-light run":       5000,
    "Wrong-side driving":  5000,
    "Stop-line violation": 500,
    "Illegal parking":     500,
}

# ─── Camera metadata template ─────────────────────────────────────────────────
# Populate from your camera registry database
CAMERA_DEFAULTS = {
    "resolution":      "1080p",
    "fps":             30,
    "location":        "Unknown",
    "zone":            "General",
    "historical_fp":   0.05,   # default 5% false positive rate
}