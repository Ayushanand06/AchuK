# preprocessing.py — Image enhancement pipeline
# Handles: low light, rain, motion blur, shadow, glare

import cv2
import numpy as np
from collections import deque
from app.config import (
    CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID,
    FRAME_BUFFER_SIZE, TARGET_WIDTH
)


class ImagePreprocessor:
    """
    Full preprocessing pipeline for traffic camera frames.

    Steps applied in order:
      1. Resize to standard width (preserving aspect ratio)
      2. CLAHE equalisation for low-light / high-contrast scenes
      3. Temporal frame averaging to suppress motion blur
      4. Shadow removal via illumination normalisation
      5. Rain-streak suppression via guided filter
    """

    def __init__(self):
        self.clahe = cv2.createCLAHE(
            clipLimit=CLAHE_CLIP_LIMIT,
            tileGridSize=CLAHE_TILE_GRID
        )
        self._frame_buffer = deque(maxlen=FRAME_BUFFER_SIZE)

    # ── Public entry point ────────────────────────────────────────────────────

    def process(self, frame: np.ndarray, is_video: bool = False) -> np.ndarray:
        """
        Run the full pipeline on a single frame.
        Set is_video=True when processing a video stream so temporal
        averaging is applied.
        """
        frame = self._resize(frame)
        frame = self._enhance_lighting(frame)
        if is_video:
            frame = self._temporal_average(frame)
        frame = self._remove_shadows(frame)
        frame = self._suppress_rain(frame)
        return frame

    def process_light(self, frame: np.ndarray) -> np.ndarray:
        """
        Fast preprocess for live feeds: resize + CLAHE only. Skips the costly
        shadow-removal, rain-suppression and temporal-averaging steps so the GPU
        isn't stalled by CPU image work. Same resize, so pixel calibration holds.
        """
        return self._enhance_lighting(self._resize(frame))

    # ── Step 1: Resize ────────────────────────────────────────────────────────

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if w == TARGET_WIDTH:
            return frame
        scale = TARGET_WIDTH / w
        new_h = int(h * scale)
        return cv2.resize(frame, (TARGET_WIDTH, new_h),
                          interpolation=cv2.INTER_LINEAR)

    # ── Step 2: CLAHE lighting enhancement ───────────────────────────────────

    def _enhance_lighting(self, frame: np.ndarray) -> np.ndarray:
        """
        Convert to LAB colour space, apply CLAHE only to the L (luminance)
        channel, then convert back. This avoids colour distortion while
        improving local contrast — critical for night-time footage.
        """
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_eq = self.clahe.apply(l)
        lab_eq = cv2.merge([l_eq, a, b])
        return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

    # ── Step 3: Temporal averaging (motion-blur reduction) ───────────────────

    def _temporal_average(self, frame: np.ndarray) -> np.ndarray:
        """
        Average the last N frames to reduce motion blur from fast vehicles.
        Only meaningful in video mode; single-frame mode skips this.
        """
        self._frame_buffer.append(frame.astype(np.float32))
        if len(self._frame_buffer) < 2:
            return frame
        avg = np.mean(np.array(self._frame_buffer), axis=0)
        return np.clip(avg, 0, 255).astype(np.uint8)

    # ── Step 4: Shadow removal ────────────────────────────────────────────────

    def _remove_shadows(self, frame: np.ndarray) -> np.ndarray:
        """
        Shadows cause dark regions that confuse helmet/seatbelt detectors.
        Strategy: dilate each channel with a large kernel to estimate the
        background illumination, then subtract it and normalise.
        """
        rgb_planes = cv2.split(frame)
        result_planes = []
        kernel = np.ones((7, 7), np.uint8)

        for plane in rgb_planes:
            dilated = cv2.dilate(plane, kernel)
            bg = cv2.medianBlur(dilated, 21)
            diff = 255 - cv2.absdiff(plane, bg)
            norm = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
            result_planes.append(norm)

        return cv2.merge(result_planes)

    # ── Step 5: Rain-streak suppression ──────────────────────────────────────

    def _suppress_rain(self, frame: np.ndarray) -> np.ndarray:
        """
        Rain streaks appear as near-vertical high-frequency noise.
        A guided filter smooths streaks while preserving edges
        (unlike Gaussian blur which blurs license plates too).
        """
        # guided filter approximation via bilateral filter
        # (OpenCV's ximgproc.guidedFilter needs the contrib build)
        return cv2.bilateralFilter(frame, d=5, sigmaColor=50, sigmaSpace=50)

    # ── Utility: estimate lighting score (0–1) ────────────────────────────────

    @staticmethod
    def lighting_score(frame: np.ndarray) -> float:
        """
        Returns a normalised luminance score used by the CVCS module.
        0.0 = very dark (low confidence), 1.0 = well-lit.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_lum = float(np.mean(gray)) / 255.0
        # penalise both too dark (<0.3) and overexposed (>0.85)
        if mean_lum < 0.3:
            return mean_lum / 0.3            # scale 0→1 over dark range
        if mean_lum > 0.85:
            return 1.0 - (mean_lum - 0.85) / 0.15
        return 1.0

    # ── Utility: estimate vehicle speed proxy from frame delta ────────────────

    @staticmethod
    def motion_magnitude(prev: np.ndarray, curr: np.ndarray) -> float:
        """
        Returns normalised pixel-motion magnitude between two consecutive
        frames (0 = static, 1 = fast-moving). Used to weight OCR confidence.
        A slowly moving / stopped vehicle gives cleaner plate reads.
        """
        g1 = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(g1, g2).astype(np.float32)
        return float(np.mean(diff)) / 255.0