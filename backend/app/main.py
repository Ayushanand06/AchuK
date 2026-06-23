
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.settings import settings
from app.config import OUTPUT_DIR
from app.routers import (
    health, violations, challans, analytics, jobs, cameras, live,
    map as map_router,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in (OUTPUT_DIR, settings.videos_dir, settings.frames_dir,
              settings.uploads_dir, settings.calibration_dir, settings.live_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    log.info("Output dir: %s", OUTPUT_DIR)
    log.info("Models dir: %s", settings.models_dir)
    log.info("Mappls configured: %s", settings.mappls_configured)
    yield
    from app.services.live_feed import manager as live_manager
    live_manager.stop()


app = FastAPI(
    title="VisionEnforce — Traffic Violation Detection API",
    description=(
        "Automated photo identification and classification for traffic "
        "violations. Upload a photo to detect helmet/seatbelt/triple-riding "
        "violations, read the plate, score confidence, and issue a challan."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for _d in (OUTPUT_DIR, settings.videos_dir, settings.frames_dir):
    Path(_d).mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=OUTPUT_DIR), name="evidence")
app.mount("/videos", StaticFiles(directory=settings.videos_dir), name="videos")
app.mount("/frames", StaticFiles(directory=settings.frames_dir), name="frames")

app.include_router(health.router)
app.include_router(violations.router)
app.include_router(challans.router)
app.include_router(analytics.router)
app.include_router(jobs.router)
app.include_router(cameras.router)
app.include_router(live.router)
app.include_router(map_router.router)


@app.get("/", tags=["health"])
def root():
    return {
        "service": "VisionEnforce Traffic Violation API",
        "docs": "/docs",
        "health": "/api/health",
    }
