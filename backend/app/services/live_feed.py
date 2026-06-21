# live_feed.py — continuous multi-camera "live feed" simulation.
#
# Each registered camera is bound to a looping video clip. A single background
# thread round-robins the cameras, runs one detection step per visit, writes the
# camera's latest annotated frame to disk, and tracks live stats. This mimics N
# live junction streams for the operations wall.
#
# CPU-realistic: it processes ~one frame at a time across cameras (not 25fps).

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
        self._feeds: Dict[str, str] = {}          # camera_id -> video path
        self._caps: Dict[str, cv2.VideoCapture] = {}
        self._pipes: Dict[str, VideoPipeline] = {}
        self._stats: Dict[str, dict] = {}
        self._tick = 0.05                          # small breather between frames
        self._stride = settings.live_stride        # frames skipped between reads

    # ── Feed mapping ─────────────────────────────────────────────────────────────

    def _resolve_feeds(self) -> Dict[str, str]:
        """
        feeds.json ({camera_id: path}) if present; otherwise loop the first clip
        found in feeds_dir across every registered camera.
        """
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
            Path(settings.live_dir).mkdir(parents=True, exist_ok=True)

            for cam, path in self._feeds.items():
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    log.warning("Cannot open feed for %s: %s", cam, path)
                    continue
                self._caps[cam] = cap
                self._pipes[cam] = VideoPipeline(cam)
                self._stats[cam] = {
                    "camera_id": cam,
                    "location": camera_registry.camera_meta(cam)["location"],
                    "zone": camera_registry.camera_meta(cam)["zone"],
                    "clip": os.path.basename(path),
                    "frames": 0, "violations": 0, "by_type": {},
                    "signal_state": "unknown", "last_seen": None, "online": True,
                }

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            log.info("Live feeds started: %d cameras", len(self._caps))
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
        log.info("Live feeds stopped")
        return self.status()

    # ── Worker ───────────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            for cam, cap in list(self._caps.items()):
                if not self._running:
                    break
                ok, raw = cap.read()
                if not ok:                       # clip ended → loop it
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, raw = cap.read()
                    if not ok:
                        continue
                # Stride forward (decode-free grabs) so each processed frame
                # samples deeper into the clip — violations surface fast.
                for _ in range(self._stride):
                    if not cap.grab():
                        break
                try:
                    annotated, issued, info = self._pipes[cam].step(raw, time.time())
                except Exception as exc:         # never let one camera kill the loop
                    log.exception("step failed for %s: %s", cam, exc)
                    continue

                self._write_frame(cam, annotated)
                st = self._stats[cam]
                st["frames"] += 1
                st["signal_state"] = info["signal_state"]
                st["last_seen"] = datetime.now(timezone.utc).isoformat()
                for rec in issued:
                    st["violations"] += 1
                    st["by_type"][rec.violation_type] = st["by_type"].get(rec.violation_type, 0) + 1

                time.sleep(self._tick)

    def _write_frame(self, cam: str, frame):
        # Atomic write so the HTTP reader never sees a half-written JPEG.
        dst = Path(settings.live_dir) / f"{cam}.jpg"
        tmp = Path(settings.live_dir) / f".{cam}.tmp.jpg"
        cv2.imwrite(str(tmp), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        os.replace(tmp, dst)

    # ── Read side ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {"running": self._running, "cameras": list(self._stats.values())}

    def frame_path(self, cam: str) -> Optional[str]:
        p = Path(settings.live_dir) / f"{cam}.jpg"
        return str(p) if p.exists() else None


manager = LiveFeedManager()
