# AchuK — Traffic Violation Detection Backend

FastAPI backend for **Automated Photo Identification and Classification for
Traffic Violations**. Upload a traffic photo → detect violations across four
YOLOv8 models → read the number plate (OCR) → score confidence (CVCS) → issue a
tamper-evident challan with annotated evidence → analytics + Mappls map data.

## Stack
- **FastAPI** + Uvicorn (API)
- **Ultralytics YOLOv8** — 4 models: helmet, seatbelt, triple-riding, plate
- **EasyOCR** (PaddleOCR optional) — number-plate recognition
- **OpenCV** — preprocessing + annotation
- **Mappls (MapMyIndia)** — geocoding, routes, nearby, map data
- File-based JSON store for challan records (`output/challans/`)

## Setup (uv)

```bash
cd backend
cp .env.example .env        # optional: add Mappls keys
uv sync                     # creates .venv on Python 3.12, installs deps
uv run uvicorn app.main:app --reload
```

Open the interactive docs at <http://127.0.0.1:8000/docs>.

> First request that touches a model triggers a one-time load (helmet.pt is
> ~200 MB). Call `GET /api/health/models` once to warm up and to print each
> model's class labels.

### GPU / CPU

`torch`/`torchvision` are pinned to the **CUDA 12.4** build, so on a machine with
an NVIDIA GPU a plain `uv sync` installs CUDA wheels and the YOLO models **and**
EasyOCR use the GPU automatically — no code changes. These wheels also run on
CPU-only machines (they just won't find a GPU).

- **Older NVIDIA driver:** change the index URL in `pyproject.toml`
  (`[[tool.uv.index]]`) from `.../whl/cu124` to `.../whl/cu121`, then `uv lock`.
- **Lean CPU-only install:** point it at `.../whl/cpu` (much smaller download).

> Uses Git LFS for model weights — run `git lfs install` once, then `git lfs pull`.

## Project layout

```
app/
  main.py            FastAPI app (CORS, /evidence static mount, routers)
  settings.py        env-driven settings (.env)
  config.py          constants + model paths + MODEL_VIOLATION_MAP
  domain/            ML/domain logic (detector, ocr, cvcs, challan, analytics, ...)
  services/          inference cache, photo_pipeline, camera_registry, store
  routers/           health, violations, challans, analytics, map
  schemas/           pydantic response models
models/              helmet.pt, yolov8_seatbelt.pt, yolov8_triple.pt, yolov8_plate.pt
configs/cameras/     camera_id -> lat/lng/zone registry
output/challans/     generated evidence + record.json (gitignored)
```

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/violations/detect` | Upload image (+ `camera_id`) → violations + challans |
| GET  | `/api/challans` | Search records (`violation_type`, `zone`, `plate`, `date`, ...) |
| GET  | `/api/challans/{id}` | Single challan record |
| GET  | `/api/analytics/weekly` | Weekly summary (totals, by-type/zone/hour/day, WoW) |
| GET  | `/api/analytics/kpis` | Enforcement KPIs |
| GET  | `/api/analytics/patrol` | Predictive patrol recommendations |
| GET  | `/api/map-data` | Pins + heatmap + routes + summary for the Mappls dashboard |
| GET  | `/api/map/cameras` | Registered camera nodes |
| GET  | `/api/health/models` | Load models + report class labels |
| GET  | `/evidence/...` | Annotated evidence images (static) |

## Detected violations (photo set)
Helmet non-compliance, seatbelt non-compliance, triple riding, and license-plate
recognition. Rule-based violations (red-light, wrong-side, stop-line, illegal
parking) require video + per-camera calibration and are out of scope for this
photo build.

## Notes
- Without Mappls credentials the app still runs: `/api/map-data` builds pins and
  heatmap locally from the camera registry; only `geocode` / `nearby-police` /
  route polylines need keys.
- If `GET /api/health/models` shows unexpected class labels, update
  `MODEL_VIOLATION_MAP` in `app/config.py` to match your weights.
