
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mapmyindia_api_key: str = ""
    mapmyindia_client_id: str = ""
    mapmyindia_client_secret: str = ""

    output_dir: str = str(BACKEND_DIR / "output" / "challans")
    models_dir: str = str(BACKEND_DIR / "models")
    cameras_dir: str = str(BACKEND_DIR / "configs" / "cameras")
    calibration_dir: str = str(BACKEND_DIR / "configs" / "cameras" / "calibration")
    uploads_dir: str = str(BACKEND_DIR / "output" / "uploads")
    videos_dir: str = str(BACKEND_DIR / "output" / "videos")
    frames_dir: str = str(BACKEND_DIR / "output" / "frames")
    live_dir: str = str(BACKEND_DIR / "output" / "live")
    feeds_dir: str = str(BACKEND_DIR / "trafficVideo")
    live_stride: int = 20
    live_tick: float = 0.02
    live_target_fps: int = 15
    live_light_preprocess: bool = True

    helmet_model_file: str = "helmet.pt"
    seatbelt_model_file: str = "yolov8_seatbelt.pt"
    triple_model_file: str = "triple_riding.pt"
    plate_model_file: str = "yolov8_plate.pt"
    vehicle_model_file: str = "yolov8n.pt"

    yolo_conf_threshold: float = 0.45
    yolo_iou_threshold: float = 0.45
    inference_imgsz: int = 640

    video_skip_frames: int = 2
    dedup_cooldown_sec: float = 10.0

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
        p = Path(self.models_dir) / self.vehicle_model_file
        return str(p) if p.exists() else self.vehicle_model_file

    @property
    def mappls_configured(self) -> bool:
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
