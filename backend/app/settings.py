# settings.py — environment-driven configuration (pydantic-settings)
#
# All values can be overridden via a .env file in the backend/ directory
# or via real environment variables. See .env.example for the template.

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  (parent of app/)
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Mappls / MapMyIndia credentials (optional — app runs without them) ──────
    mapmyindia_api_key: str = ""
    mapmyindia_client_id: str = ""
    mapmyindia_client_secret: str = ""

    # ── Paths ──────────────────────────────────────────────────────────────────
    # Where challan evidence + JSON records are written/read.
    output_dir: str = str(BACKEND_DIR / "output" / "challans")
    # Where the .pt model weights live.
    models_dir: str = str(BACKEND_DIR / "models")
    # Camera registry directory (camera_id -> lat/lng/zone JSON files).
    cameras_dir: str = str(BACKEND_DIR / "configs" / "cameras")
    # Per-camera calibration files (camera_id -> calibration JSON).
    calibration_dir: str = str(BACKEND_DIR / "configs" / "cameras" / "calibration")
    # Uploaded video clips awaiting / during processing.
    uploads_dir: str = str(BACKEND_DIR / "output" / "uploads")
    # Annotated output videos (served at /videos).
    videos_dir: str = str(BACKEND_DIR / "output" / "videos")
    # Grabbed calibration frames (served at /frames).
    frames_dir: str = str(BACKEND_DIR / "output" / "frames")
    # Latest annotated frame per camera for the live wall.
    live_dir: str = str(BACKEND_DIR / "output" / "live")
    # Directory scanned for demo feed clips when feeds.json is absent.
    feeds_dir: str = str(BACKEND_DIR / "trafficVideo")
    # Frames to skip between processed frames on a live feed (samples deeper into
    # the clip each tick so violations surface quickly despite CPU limits).
    live_stride: int = 20

    # ── Model filenames (inside models_dir) ────────────────────────────────────
    helmet_model_file: str = "helmet.pt"
    seatbelt_model_file: str = "yolov8_seatbelt.pt"
    triple_model_file: str = "triple_riding.pt"
    plate_model_file: str = "yolov8_plate.pt"
    # General COCO detector for vehicle bboxes (auto-downloaded by ultralytics).
    vehicle_model_file: str = "yolov8n.pt"

    # ── Detection thresholds (override config.py defaults if set) ───────────────
    yolo_conf_threshold: float = 0.45
    yolo_iou_threshold: float = 0.45
    # Inference resolution for the detection models (helmet/seatbelt/triple/
    # vehicle). Smaller = much faster on CPU; boxes still map to full-frame
    # coords so calibration is unaffected. The plate model is exempt.
    inference_imgsz: int = 640

    # ── Video processing ───────────────────────────────────────────────────────
    # Process every (skip_frames + 1)th frame; cooldown to suppress duplicate
    # challans for the same ongoing violation.
    video_skip_frames: int = 2
    dedup_cooldown_sec: float = 10.0

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed frontend origins; "*" allows all (dev).
    cors_origins: str = "*"

    @property
    def helmet_model_path(self) -> str:
        return str(Path(self.models_dir) / self.helmet_model_file)

    @property
    def seatbelt_model_path(self) -> str:
        return str(Path(self.models_dir) / self.seatbelt_model_file)

    @property
    def triple_model_path(self) -> str:
        return str(Path(self.models_dir) / self.triple_model_file)

    @property
    def plate_model_path(self) -> str:
        return str(Path(self.models_dir) / self.plate_model_file)

    @property
    def vehicle_model_path(self) -> str:
        # If the file is missing, ultralytics treats the bare name as a known
        # model and downloads it; keep the name so that fallback works.
        p = Path(self.models_dir) / self.vehicle_model_file
        return str(p) if p.exists() else self.vehicle_model_file

    @property
    def mappls_configured(self) -> bool:
        # A single static REST key is enough; OAuth client id/secret also works.
        return bool(
            self.mapmyindia_api_key
            or (self.mapmyindia_client_id and self.mapmyindia_client_secret)
        )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
