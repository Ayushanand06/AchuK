
import re
from app.settings import settings

HELMET_MODEL       = settings.helmet_model_path
SEATBELT_MODEL     = settings.seatbelt_model_path
TRIPLE_MODEL       = settings.triple_model_path
PLATE_DETECT_MODEL = settings.plate_model_path

MAPMYINDIA_API_KEY       = settings.mapmyindia_api_key
MAPMYINDIA_CLIENT_ID     = settings.mapmyindia_client_id
MAPMYINDIA_CLIENT_SECRET = settings.mapmyindia_client_secret

CLASS_NAMES = {
    0:  "person",        1:  "bicycle",     2:  "motorcycle",  3:  "car",
    4:  "bus",           5:  "truck",       6:  "helmet",      7:  "no_helmet",
    8:  "seatbelt",      9:  "no_seatbelt", 10: "license_plate",11: "triple_riding",
    12: "stop_line",     13: "red_light",   14: "green_light", 15: "wrong_side",
}

MODEL_VIOLATION_MAP = {
    "helmet": {
        "no_helmet":       "No helmet",
        "no-helmet":       "No helmet",
        "nohelmet":        "No helmet",
        "without_helmet":  "No helmet",
        "without helmet":  "No helmet",
        "helmetless":      "No helmet",
        "head":            "No helmet",
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
        "tripple":         "Triple riding",
        "triple_riding":   "Triple riding",
        "triples":         "Triple riding",
        "overload":        "Triple riding",
    },
}

MOTORCYCLE_KEYWORDS = ("motorcycle", "motorbike", "bike", "scooter", "two_wheeler", "twowheeler")
PERSON_KEYWORDS     = ("person", "rider", "people", "passenger", "motorcyclist", "head")

VEHICLE_CLASS_IDS = {2, 3, 5, 7}

DEDUP_COOLDOWN_SEC = settings.dedup_cooldown_sec
VIDEO_SKIP_FRAMES  = settings.video_skip_frames

YOLO_CONF_THRESHOLD   = settings.yolo_conf_threshold
YOLO_IOU_THRESHOLD    = settings.yolo_iou_threshold
CVCS_AUTO_THRESHOLD   = 0.80
CVCS_REVIEW_THRESHOLD = 0.55

OCR_UPSCALE_FACTOR    = 4
OCR_MIN_CONFIDENCE    = 0.60
PLATE_ASPECT_MIN      = 2.0
PLATE_ASPECT_MAX      = 6.0

PLATE_REGEX = re.compile(
    r"^[A-Z]{2}[\s-]?[0-9]{1,2}[\s-]?[A-Z]{1,2}[\s-]?[0-9]{4}$"
)

CLAHE_CLIP_LIMIT      = 2.0
CLAHE_TILE_GRID       = (8, 8)
FRAME_BUFFER_SIZE     = 5
TARGET_WIDTH          = 1280

CVCS_WEIGHTS = {
    "model_conf":      0.40,
    "resolution":      0.20,
    "lighting":        0.15,
    "vehicle_speed":   0.10,
    "camera_history":  0.15,
}

OUTPUT_DIR             = settings.output_dir
EVIDENCE_IMAGE_QUALITY = 95
HASH_ALGORITHM         = "sha256"

FINE_AMOUNTS = {
    "No helmet":           1000,
    "No seatbelt":         1000,
    "Triple riding":       1000,
    "Red-light run":       5000,
    "Wrong-side driving":  5000,
    "Stop-line violation": 500,
    "Illegal parking":     500,
}

CAMERA_DEFAULTS = {
    "resolution":    "1080p",
    "fps":           30,
    "location":      "Unknown",
    "zone":          "General",
    "historical_fp": 0.05,
}
