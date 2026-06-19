# cvcs.py — Contextual Violation Confidence Scoring (CVCS)
# The innovation layer: goes beyond raw model confidence

import numpy as np
from dataclasses import dataclass
from typing import Optional
from config import (
    CVCS_WEIGHTS, CVCS_AUTO_THRESHOLD, CVCS_REVIEW_THRESHOLD
)


@dataclass
class CVCSResult:
    """Full scoring breakdown for a single violation event."""
    final_score:      float       # weighted composite (0–1)
    decision:         str         # "auto_challan" | "review" | "discard"
    model_conf:       float
    resolution_score: float
    lighting_score:   float
    speed_score:      float
    camera_score:     float
    explanation:      str         # human-readable reason for decision


class CVCSEngine:
    """
    Contextual Violation Confidence Scoring.

    Why raw model confidence alone is insufficient:
    - A 0.92 confidence helmet detection on a blurry night frame is
      less trustworthy than 0.75 on a sharp daytime frame.
    - Camera nodes with known high false-positive rates should be
      down-weighted automatically.
    - Slow / stopped vehicles produce better plate OCR; fast-moving
      ones should push violations to human review even if YOLO is confident.

    The CVCS score is a weighted sum over five factors:
        final = w1*model_conf + w2*resolution + w3*lighting
                + w4*speed + w5*camera_history

    Weights are defined in config.CVCS_WEIGHTS.
    Thresholds:
        >= CVCS_AUTO_THRESHOLD   → auto challan (no human needed)
        >= CVCS_REVIEW_THRESHOLD → human review queue
        <  CVCS_REVIEW_THRESHOLD → discard (not enough evidence)
    """

    def score(
        self,
        model_conf:       float,
        frame_width:      int,
        frame_height:     int,
        lighting_score:   float,
        motion_magnitude: float,
        camera_fp_rate:   float,
        violation_type:   str,
    ) -> CVCSResult:
        """
        Compute the CVCS score for one violation detection.

        Args:
            model_conf        Raw YOLO confidence (0–1)
            frame_width       Width of the source frame in pixels
            frame_height      Height of the source frame in pixels
            lighting_score    From ImagePreprocessor.lighting_score() (0–1)
            motion_magnitude  From ImagePreprocessor.motion_magnitude() (0–1)
            camera_fp_rate    Historical false-positive rate for this camera (0–1)
            violation_type    String name of the violation
        """
        res_score    = self._resolution_score(frame_width, frame_height)
        speed_score  = self._speed_score(motion_magnitude)
        cam_score    = self._camera_score(camera_fp_rate)

        w = CVCS_WEIGHTS
        final = (
            w["model_conf"]    * model_conf    +
            w["resolution"]    * res_score     +
            w["lighting"]      * lighting_score +
            w["vehicle_speed"] * speed_score   +
            w["camera_history"]* cam_score
        )
        final = float(np.clip(final, 0.0, 1.0))

        decision, explanation = self._decide(
            final, model_conf, lighting_score, cam_score, violation_type
        )

        return CVCSResult(
            final_score      = round(final, 4),
            decision         = decision,
            model_conf       = round(model_conf, 4),
            resolution_score = round(res_score, 4),
            lighting_score   = round(lighting_score, 4),
            speed_score      = round(speed_score, 4),
            camera_score     = round(cam_score, 4),
            explanation      = explanation,
        )

    # ── Sub-scorers ───────────────────────────────────────────────────────────

    @staticmethod
    def _resolution_score(w: int, h: int) -> float:
        """
        Score based on total pixel count relative to a 1080p reference.
        1080p (2,073,600 px) → 1.0
        480p  (  307,200 px) → ~0.38
        """
        pixels = w * h
        ref    = 1920 * 1080
        return float(np.clip(pixels / ref, 0.1, 1.0))

    @staticmethod
    def _speed_score(motion_magnitude: float) -> float:
        """
        Lower motion = slower vehicle = better evidence quality.
        motion_magnitude 0.0 (static) → score 1.0
        motion_magnitude 1.0 (fast)   → score 0.1
        Linear decay.
        """
        return float(np.clip(1.0 - motion_magnitude * 0.9, 0.1, 1.0))

    @staticmethod
    def _camera_score(fp_rate: float) -> float:
        """
        Camera historical false-positive rate → trust score.
        fp_rate 0.00 (never wrong) → 1.0
        fp_rate 0.20 (20% FP)     → 0.5
        fp_rate 0.50+              → 0.1 (heavily down-weighted)
        """
        return float(np.clip(1.0 - fp_rate * 2.0, 0.1, 1.0))

    # ── Decision logic ────────────────────────────────────────────────────────

    @staticmethod
    def _decide(
        score:          float,
        model_conf:     float,
        lighting:       float,
        cam_score:      float,
        vtype:          str,
    ):
        """
        Apply thresholds and build a human-readable explanation.
        Certain violation types (wrong-side, red-light) have higher stakes
        so they route to review unless CVCS is very high (>0.88).
        """
        HIGH_STAKES = {"Red-light run", "Wrong-side driving"}

        if score >= CVCS_AUTO_THRESHOLD:
            if vtype in HIGH_STAKES and score < 0.88:
                decision = "review"
                reason   = (f"High-stakes violation ({vtype}) — routed to "
                            f"officer review even at CVCS {score:.2f}")
            else:
                decision = "auto_challan"
                reason   = (f"CVCS {score:.2f} exceeds auto threshold "
                            f"{CVCS_AUTO_THRESHOLD}. All factors strong.")
        elif score >= CVCS_REVIEW_THRESHOLD:
            decision = "review"
            weakest  = []
            if lighting < 0.5:
                weakest.append(f"low lighting ({lighting:.2f})")
            if cam_score < 0.7:
                weakest.append(f"camera trust ({cam_score:.2f})")
            if model_conf < 0.6:
                weakest.append(f"model confidence ({model_conf:.2f})")
            weak_str = ", ".join(weakest) if weakest else "borderline score"
            reason   = (f"CVCS {score:.2f} — routed to review due to: "
                        f"{weak_str}.")
        else:
            decision = "discard"
            reason   = (f"CVCS {score:.2f} below discard threshold "
                        f"{CVCS_REVIEW_THRESHOLD}. Evidence insufficient "
                        f"for enforcement action.")

        return decision, reason