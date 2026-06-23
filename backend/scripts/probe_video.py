
import sys
from collections import defaultdict

import cv2

from app.services.inference import (
    get_helmet_model, get_seatbelt_model, get_triple_model, get_vehicle_model,
)
from app.services.inference import get_detector
from app.config import VEHICLE_CLASS_IDS, YOLO_CONF_THRESHOLD


def raw_counts(model, frame, agg):
    res = model(frame, verbose=False)[0]
    names = model.names
    for b in res.boxes:
        name = str(names.get(int(b.cls[0]), "?"))
        conf = float(b.conf[0])
        agg[name]["n"] += 1
        agg[name]["max"] = max(agg[name]["max"], conf)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "trafficVideo/gettyimages-1164849900-640_adpp.mp4"
    sample_every = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print("Cannot open:", path); return
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video: {path}\n  {w}x{h} @ {fps:.1f}fps, {total} frames")
    print(f"  conf threshold = {YOLO_CONF_THRESHOLD}, sampling every {sample_every} frames\n")

    helmet, seatbelt, triple, vehicle = (
        get_helmet_model(), get_seatbelt_model(), get_triple_model(), get_vehicle_model())
    detector = get_detector()

    aggs = {k: defaultdict(lambda: {"n": 0, "max": 0.0})
            for k in ["helmet", "seatbelt", "triple", "vehicle"]}
    violation_counts = defaultdict(int)
    vehicle_frames = 0
    processed = 0
    fi = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        fi += 1
        if fi % sample_every:
            continue
        processed += 1
        raw_counts(helmet, frame, aggs["helmet"])
        raw_counts(seatbelt, frame, aggs["seatbelt"])
        raw_counts(triple, frame, aggs["triple"])
        raw_counts(vehicle, frame, aggs["vehicle"])

        vres = vehicle(frame, verbose=False)[0]
        if any(int(b.cls[0]) in VEHICLE_CLASS_IDS and float(b.conf[0]) >= YOLO_CONF_THRESHOLD
               for b in vres.boxes):
            vehicle_frames += 1

        viols, _ = detector.detect(frame, {})
        for v in viols:
            violation_counts[v.violation_type] += 1

    cap.release()
    print(f"Sampled {processed} frames.\n")
    for model_name, agg in aggs.items():
        print(f"[{model_name}] raw detections (class: count, maxconf):")
        if not agg:
            print("   (none)")
        for cls, d in sorted(agg.items(), key=lambda x: -x[1]["n"]):
            print(f"   {cls:20} n={d['n']:<4} max={d['max']:.2f}")
        print()
    print("Vehicle-present frames:", vehicle_frames, "/", processed)
    print("\nMultiModelDetector violations (across sampled frames):")
    if not violation_counts:
        print("   (none)")
    for t, n in violation_counts.items():
        print(f"   {t:20} {n}")


if __name__ == "__main__":
    main()
