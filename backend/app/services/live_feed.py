# live_feed.py — continuous multi-camera "live feed" simulation.
#
# A single background thread drives the cameras: each visit decodes one frame,
# runs a detection step, keeps the latest annotated JPEG in memory (for MJPEG
# streaming) and tracks live stats. A "focus" camera is processed every loop
# iteration (full rate) while the rest round-robin — so on a modest GPU one feed
# can run smoothly while the others still update.

import os
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

import cv2

from app.settings import settings
from app.services import camera_registry
from app.services.video_pipeline import VideoPipeline

log = logging.getLogger("live_feed")


class LiveFeedManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._feeds: Dict[str, str] = {}              # camera_id -> video path
        self._caps: Dict[str, cv2.VideoCapture] = {}
        self._pipes: Dict[str, VideoPipeline] = {}
        self._stats: Dict[str, dict] = {}
        self._latest: Dict[str, bytes] = {}           # camera_id -> latest JPEG bytes
        self._focus: Optional[str] = None
        self._rr = 0
        self._tick = settings.live_tick
        self._stride = settings.live_stride

    # ── Feed mapping ─────────────────────────────────────────────────────────────

    def _resolve_feeds(self) -> Dict[str, str]:
        cfg = Path(settings.cameras_dir) / "feeds.json"
        if cfg.exists():
            try:
                raw = json.loads(cfg.read_text(encoding="utf-8"))
                return {k: self._abs(v) for k, v in raw.items()}
            except Exception as exc:
                log.warning("Bad feeds.json: %s", exc)

        clips = sorted(str(p) for p in Path(settings.feeds_dir).glob("*.mp4"))
        cams = list(camera_registry.all_cameras().keys())
        if not clips or not cams:
            return {}
        return {cam: clips[i % len(clips)] for i, cam in enumerate(cams)}

    @staticmethod
    def _abs(p: str) -> str:
        path = Path(p)
        return str(path if path.is_absolute() else Path(settings.feeds_dir).parent / p)

    # ── Lifecycle ────────────────────────────────────────────────────────────────

    def start(self) -> dict:
        with self._lock:
            if self._running:
                return self.status()
            self._feeds = self._resolve_feeds()
            if not self._feeds:
                raise RuntimeError("No feed clips found. Add an .mp4 to trafficVideo/.")

            for cam, path in self._feeds.items():
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    log.warning("Cannot open feed for %s: %s", cam, path)
                    continue
                self._caps[cam] = cap
                self._pipes[cam] = VideoPipeline(cam, light=settings.live_light_preprocess)
                meta = camera_registry.camera_meta(cam)
                self._stats[cam] = {
                    "camera_id": cam, "location": meta["location"], "zone": meta["zone"],
                    "clip": os.path.basename(path),
                    "frames": 0, "violations": 0, "by_type": {},
                    "signal_state": "unknown", "last_seen": None, "online": True,
                }

            if not self._focus and self._caps:
                self._focus = next(iter(self._caps))   # default focus = first camera
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            log.info("Live feeds started: %d cameras (focus=%s)", len(self._caps), self._focus)
            return self.status()

    def stop(self) -> dict:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        for cap in self._caps.values():
            try:
                cap.release()
            except Exception:
                pass
        self._caps.clear()
        self._pipes.clear()
        self._latest.clear()
        log.info("Live feeds stopped")
        return self.status()

    def set_focus(self, camera_id: Optional[str]) -> dict:
        if camera_id and camera_id in self._caps:
            self._focus = camera_id
        elif camera_id is None:
            self._focus = None
        return self.status()

    # ── Worker ───────────────────────────────────────────────────────────────────

    def _process(self, cam: str):
        cap = self._caps.get(cam)
        if cap is None:
            return
        ok, raw = cap.read()
        if not ok:                                # clip ended → loop it
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, raw = cap.read()
            if not ok:
                return
        # Stride only the non-focus cameras (focus stays frame-accurate/smooth).
        if cam != self._focus:
            for _ in range(self._stride):
                if not cap.grab():
                    break
        try:
            annotated, issued, info = self._pipes[cam].step(raw, time.time())
        except Exception as exc:
            log.exception("step failed for %s: %s", cam, exc)
            return

        ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            self._latest[cam] = buf.tobytes()
        st = self._stats[cam]
        st["frames"] += 1
        st["signal_state"] = info["signal_state"]
        st["last_seen"] = datetime.now(timezone.utc).isoformat()
        for rec in issued:
            st["violations"] += 1
            st["by_type"][rec.violation_type] = st["by_type"].get(rec.violation_type, 0) + 1

    def _loop(self):
        while self._running:
            cams = list(self._caps.keys())
            if not cams:
                break
            schedule: List[str] = []
            if self._focus in self._caps:
                schedule.append(self._focus)          # focus every iteration = full rate
            others = [c for c in cams if c != self._focus]
            if others:
                schedule.append(others[self._rr % len(others)])
                self._rr += 1
            for cam in schedule:
                if not self._running:
                    break
                self._process(cam)
            time.sleep(self._tick)

    # ── Read side ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {"running": self._running, "focus": self._focus,
                "cameras": list(self._stats.values())}

    def latest_jpeg(self, cam: str) -> Optional[bytes]:
        return self._latest.get(cam)

    @property
    def running(self) -> bool:
        return self._running


manager = LiveFeedManager()
