# Diagnostic: run the plate model + OCR over sampled frames of a clip.
# Usage: uv run python scripts/probe_plates.py <path> [sample_every]

import sys
import cv2

from app.services.inference import get_ocr


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "trafficVideo/gettyimages-1164849900-640_adpp.mp4"
    sample_every = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    ocr = get_ocr()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print("Cannot open:", path); return

    plate_boxes = 0          # raw plate detections from the plate YOLO
    box_sizes = []           # (w,h) of detected plate boxes
    read_attempts = 0
    reads = []               # (text, conf, valid)
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

        boxes = ocr.find_plates(frame)
        plate_boxes += len(boxes)
        for b in boxes:
            box_sizes.append((b[2] - b[0], b[3] - b[1]))
            read_attempts += 1
            res = ocr.extract(frame, b)
            if res:
                reads.append((res.cleaned_text, round(res.ocr_conf, 2), res.is_valid))

    cap.release()
    print(f"Sampled {processed} frames")
    print(f"Raw plate boxes detected: {plate_boxes}")
    if box_sizes:
        ws = sorted(w for w, h in box_sizes)
        hs = sorted(h for w, h in box_sizes)
        print(f"Plate box width  px: min={ws[0]} median={ws[len(ws)//2]} max={ws[-1]}")
        print(f"Plate box height px: min={hs[0]} median={hs[len(hs)//2]} max={hs[-1]}")
    print(f"OCR extract() returned text: {len(reads)} / {read_attempts} attempts")
    valid = [r for r in reads if r[2]]
    print(f"Format-valid plates: {len(valid)}")
    print("\nSample reads (text, conf, valid):")
    for r in reads[:25]:
        print("  ", r)


if __name__ == "__main__":
    main()
