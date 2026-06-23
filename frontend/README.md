# AchuK — Frontend (Traffic Violation Intelligence)

React + Vite (plain JS) dashboard implementing the **Analytics & reporting**
design, wired to the FastAPI backend.

## Run

```bash
# 1. Start the backend (separate terminal)
cd ../backend
uv run uvicorn app.main:app --reload      # serves on http://127.0.0.1:8000

# 2. Start the frontend
cd frontend
npm install
npm run dev                               # http://localhost:5173
```

The Vite dev server proxies `/api`, `/evidence`, `/videos`, `/frames` to the
backend (see `vite.config.js`), so no CORS setup is needed in development.

## What it shows
- **Violation trend** — daily detections this week (`/api/analytics/weekly`)
- **Decision split** — auto-issued vs reviewed (`/api/analytics/weekly`)
- **Zone × hour heatmap** — `/api/analytics/zone-hour`
- **Camera false-positive table** — `/api/analytics/camera-report`
- **Search** — Plate / Challan ID / Zone / Date over `/api/challans`

Panels show "no data" placeholders until detections have been run. Run a
detection (`POST /api/violations/detect` with a real photo, `camera_id=CAM-001`)
to populate them.

## Structure
```
src/
  theme.js            color + font tokens
  api.js              backend fetch helpers
  pages/AnalyticsPage.jsx   layout + data loading
  components/         Header, SearchBar, SearchResults, TrendChart,
                      DecisionDonut, ZoneHourHeatmap, CameraTable, Panel
```

Build for production: `npm run build` → `dist/`.
