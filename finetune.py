# finetune.py — YOLOv8 fine-tuning for visual violation detection


import os
import yaml
import shutil
from pathlib import Path
from ultralytics import YOLO


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION — edit these paths after downloading your datasets
# ══════════════════════════════════════════════════════════════════════════════

DATASET_ROOTS = {
    "helmet":    "datasets/helmet/",         # ← paste your dataset path here
    "seatbelt":  "datasets/seatbelt/",       # ← paste your dataset path here
    "triple":    "datasets/triple_riding/",  # ← paste your dataset path here
    "plate":     "datasets/license_plate/",  # ← paste your dataset path here
}

# Expected subfolder layout inside each dataset root:
#   images/train/   images/val/
#   labels/train/   labels/val/
# (Standard YOLOv8 / Roboflow export format)

BASE_MODEL   = "yolov8m.pt"   # start from YOLOv8-medium pretrained on COCO
OUTPUT_DIR   = "models/"
EPOCHS       = 50             # increase to 100 for better accuracy
IMG_SIZE     = 640
BATCH_SIZE   = 16             # reduce to 8 if GPU VRAM < 8GB
DEVICE       = "0"            # "0" for GPU, "cpu" for CPU-only


# ══════════════════════════════════════════════════════════════════════════════
#  DATASET YAML GENERATORS
#  YOLOv8 requires a .yaml file describing each dataset.
#  These functions create them automatically from your folder structure.
# ══════════════════════════════════════════════════════════════════════════════

def make_helmet_yaml() -> str:
    """
    Classes:
        0: helmet
        1: no_helmet
    Both classes needed — the model must learn what a helmet looks like
    in order to confidently flag its absence.
    """
    config = {
        "path":  str(Path(DATASET_ROOTS["helmet"]).resolve()),
        "train": "images/train",
        "val":   "images/val",
        "nc":    2,
        "names": {0: "helmet", 1: "no_helmet"},
    }
    return _write_yaml(config, "helmet_data.yaml")


def make_seatbelt_yaml() -> str:
    """
    Classes:
        0: seatbelt
        1: no_seatbelt
    Camera angle matters here: front-facing dashcams or side-facing
    intersection cameras give the best torso visibility.
    """
    config = {
        "path":  str(Path(DATASET_ROOTS["seatbelt"]).resolve()),
        "train": "images/train",
        "val":   "images/val",
        "nc":    2,
        "names": {0: "seatbelt", 1: "no_seatbelt"},
    }
    return _write_yaml(config, "seatbelt_data.yaml")


def make_triple_riding_yaml() -> str:
    """
    Classes:
        0: person
        1: motorcycle
        2: bicycle
    Triple riding is inferred in post-processing by counting persons
    overlapping a single motorcycle bbox (see detector.py).
    So we don't need a "triple_riding" class — just accurate person
    and motorcycle detections.
    """
    config = {
        "path":  str(Path(DATASET_ROOTS["triple"]).resolve()),
        "train": "images/train",
        "val":   "images/val",
        "nc":    3,
        "names": {0: "person", 1: "motorcycle", 2: "bicycle"},
    }
    return _write_yaml(config, "triple_data.yaml")


def make_plate_yaml() -> str:
    """
    Classes:
        0: license_plate
    Single-class detector focused on plate localisation only.
    OCR is handled separately in ocr.py.
    Training on Indian plates specifically is critical for accuracy
    because Indian plate fonts and sizes differ from Western plates.
    """
    config = {
        "path":  str(Path(DATASET_ROOTS["plate"]).resolve()),
        "train": "images/train",
        "val":   "images/val",
        "nc":    1,
        "names": {0: "license_plate"},
    }
    return _write_yaml(config, "plate_data.yaml")


# ══════════════════════════════════════════════════════════════════════════════
#  TRAINING FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def train_model(
    yaml_path:   str,
    model_name:  str,
    epochs:      int  = EPOCHS,
    img_size:    int  = IMG_SIZE,
    batch:       int  = BATCH_SIZE,
    device:      str  = DEVICE,
    augment:     bool = True,
) -> str:
    """
    Fine-tune YOLOv8 on the given dataset yaml.

    Key hyperparameters explained:
    - hsv_h / hsv_s / hsv_v: colour jitter — critical for handling
      varied Indian road lighting (day, night, monsoon)
    - mosaic: 4-image mosaic augmentation — improves small object detection
    - mixup: blends two images — helps with occlusion robustness
    - degrees / translate / scale: geometric augmentation for varied
      camera angles at Indian intersections

    Returns path to best weights file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    model = YOLO(BASE_MODEL)

    results = model.train(
        data        = yaml_path,
        epochs      = epochs,
        imgsz       = img_size,
        batch       = batch,
        device      = device,
        name        = model_name,
        project     = OUTPUT_DIR,
        exist_ok    = True,

        # ── Optimiser settings ──────────────────────────────────────────────
        optimizer   = "AdamW",    # AdamW converges better than SGD for small datasets
        lr0         = 0.001,      # initial learning rate
        lrf         = 0.01,       # final lr = lr0 * lrf
        warmup_epochs = 3,        # gradual LR warmup prevents early divergence
        cos_lr      = True,       # cosine LR schedule

        # ── Augmentation (critical for accuracy) ───────────────────────────
        # Colour augmentations — handle lighting variation
        hsv_h       = 0.015,      # hue shift
        hsv_s       = 0.7,        # saturation jitter
        hsv_v       = 0.4,        # brightness jitter

        # Geometric augmentations — handle varied camera angles
        degrees     = 5.0,        # rotation (small — cameras are fixed)
        translate   = 0.1,        # translation
        scale       = 0.5,        # zoom in/out
        shear       = 2.0,        # slight shear
        perspective = 0.0001,     # perspective distortion

        # Mosaic & mixup — improve generalisation
        mosaic      = 1.0,        # enable mosaic (set 0.0 to disable)
        mixup       = 0.1,        # mild mixup
        copy_paste  = 0.1,        # copy-paste augmentation

        # Flip augmentation
        flipud      = 0.0,        # no vertical flip (cameras are upright)
        fliplr      = 0.5,        # horizontal flip OK

        # ── Early stopping ──────────────────────────────────────────────────
        patience    = 15,         # stop if no improvement for 15 epochs

        # ── Logging ─────────────────────────────────────────────────────────
        plots       = True,       # save training curves
        save        = True,
        save_period = 10,         # save checkpoint every 10 epochs
        verbose     = True,
    )

    best_weights = os.path.join(OUTPUT_DIR, model_name, "weights", "best.pt")
    print(f"\n✓ Training complete. Best weights: {best_weights}")
    print(f"  mAP50:    {results.results_dict.get('metrics/mAP50(B)', 'N/A')}")
    print(f"  mAP50-95: {results.results_dict.get('metrics/mAP50-95(B)', 'N/A')}")
    return best_weights


def validate_model(weights_path: str, yaml_path: str):
    """
    Run validation on the held-out val set and print a full metrics report.
    Run this after training to confirm accuracy before deploying.
    """
    model   = YOLO(weights_path)
    metrics = model.val(data=yaml_path, imgsz=IMG_SIZE, device=DEVICE)

    print("\n─── Validation Metrics ────────────────────────────────────────")
    print(f"  Precision:  {metrics.results_dict.get('metrics/precision(B)', 0):.4f}")
    print(f"  Recall:     {metrics.results_dict.get('metrics/recall(B)',    0):.4f}")
    print(f"  mAP50:      {metrics.results_dict.get('metrics/mAP50(B)',     0):.4f}")
    print(f"  mAP50-95:   {metrics.results_dict.get('metrics/mAP50-95(B)', 0):.4f}")
    print(f"  F1 (approx):{2 * metrics.results_dict.get('metrics/precision(B)',0) * metrics.results_dict.get('metrics/recall(B)',0) / max(metrics.results_dict.get('metrics/precision(B)',0) + metrics.results_dict.get('metrics/recall(B)',0), 1e-6):.4f}")
    print("────────────────────────────────────────────────────────────────")
    return metrics


def merge_weights(weight_paths: dict) -> str:
    """
    After all 4 models are trained independently, this function copies
    each best.pt to the models/ directory with clean names so config.py
    can reference them directly.

    weight_paths: {
        "helmet":   "models/helmet_train/weights/best.pt",
        "seatbelt": "models/seatbelt_train/weights/best.pt",
        "triple":   "models/triple_train/weights/best.pt",
        "plate":    "models/plate_train/weights/best.pt",
    }

    NOTE: VisionEnforce runs each model separately per detection task
    (not merged into one file). This function just organises the paths.
    """
    os.makedirs("models", exist_ok=True)
    final_paths = {}
    name_map = {
        "helmet":   "yolov8_helmet.pt",
        "seatbelt": "yolov8_seatbelt.pt",
        "triple":   "yolov8_triple.pt",
        "plate":    "plate_detect.pt",
    }
    for task, src in weight_paths.items():
        dst = os.path.join("models", name_map[task])
        shutil.copy2(src, dst)
        final_paths[task] = dst
        print(f"✓ {task:10s} → {dst}")

    print("\nUpdate config.py with:")
    print(f'  MODEL_PATH         = "models/yolov8_helmet.pt"')
    print(f'  SEATBELT_MODEL     = "models/yolov8_seatbelt.pt"')
    print(f'  TRIPLE_MODEL       = "models/yolov8_triple.pt"')
    print(f'  PLATE_DETECT_MODEL = "models/plate_detect.pt"')
    return final_paths


# ══════════════════════════════════════════════════════════════════════════════
#  COCO FILTER HELPER
#  If you use COCO for triple-riding, this script extracts only the
#  person + motorcycle images (avoids downloading irrelevant categories)
# ══════════════════════════════════════════════════════════════════════════════

def filter_coco_for_triple_riding(
    coco_json:   str = "datasets/coco/annotations/instances_train2017.json",
    coco_images: str = "datasets/coco/train2017/",
    output_dir:  str = "datasets/triple_riding/",
):
    """
    Filter COCO dataset to keep only images containing both person (id=1)
    and motorcycle (id=4). Converts to YOLOv8 format automatically.

    Requires: pip install pycocotools
    """
    try:
        from pycocotools.coco import COCO
    except ImportError:
        print("Run: pip install pycocotools")
        return

    import shutil
    coco = COCO(coco_json)

    # Category IDs in COCO: person=1, motorcycle=4
    person_ids = coco.getImgIds(catIds=[1])
    moto_ids   = coco.getImgIds(catIds=[4])
    both_ids   = list(set(person_ids) & set(moto_ids))
    print(f"Found {len(both_ids)} images with both person and motorcycle")

    out_img   = os.path.join(output_dir, "images", "train")
    out_label = os.path.join(output_dir, "labels", "train")
    os.makedirs(out_img,   exist_ok=True)
    os.makedirs(out_label, exist_ok=True)

    COCO_TO_YOLO = {1: 0, 4: 1}  # person→0, motorcycle→1

    for img_id in both_ids[:5000]:  # cap at 5000 images for manageability
        img_info = coco.loadImgs(img_id)[0]
        src_path = os.path.join(coco_images, img_info["file_name"])
        if not os.path.exists(src_path):
            continue

        ann_ids = coco.getAnnIds(imgIds=img_id, catIds=[1, 4])
        anns    = coco.loadAnns(ann_ids)

        W, H = img_info["width"], img_info["height"]
        lines = []
        for ann in anns:
            cid = COCO_TO_YOLO.get(ann["category_id"])
            if cid is None:
                continue
            x, y, w, h = ann["bbox"]
            cx = (x + w / 2) / W
            cy = (y + h / 2) / H
            nw = w / W
            nh = h / H
            lines.append(f"{cid} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        if not lines:
            continue

        dst_img = os.path.join(out_img, img_info["file_name"])
        shutil.copy2(src_path, dst_img)

        label_name = os.path.splitext(img_info["file_name"])[0] + ".txt"
        with open(os.path.join(out_label, label_name), "w") as f:
            f.write("\n".join(lines))

    print(f"✓ COCO filter complete → {output_dir}")


# ── Private helpers ────────────────────────────────────────────────────────────

def _write_yaml(config: dict, filename: str) -> str:
    os.makedirs("configs", exist_ok=True)
    path = os.path.join("configs", filename)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"✓ Dataset YAML written → {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN — run all 4 training jobs sequentially
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  VisionEnforce — YOLOv8 Fine-tuning Pipeline")
    print("=" * 60)

    # Step 1 — Generate dataset YAML files
    print("\n[1/5] Generating dataset YAML configs...")
    helmet_yaml   = make_helmet_yaml()
    seatbelt_yaml = make_seatbelt_yaml()
    triple_yaml   = make_triple_riding_yaml()
    plate_yaml    = make_plate_yaml()

    # Step 2 — Train helmet model
    print("\n[2/5] Training helmet detection model...")
    helmet_weights = train_model(
        yaml_path  = helmet_yaml,
        model_name = "helmet_train",
        epochs     = 60,
    )
    validate_model(helmet_weights, helmet_yaml)

    # Step 3 — Train seatbelt model
    print("\n[3/5] Training seatbelt detection model...")
    seatbelt_weights = train_model(
        yaml_path  = seatbelt_yaml,
        model_name = "seatbelt_train",
        epochs     = 50,
    )
    validate_model(seatbelt_weights, seatbelt_yaml)

    # Step 4 — Train triple-riding model
    print("\n[4/5] Training triple-riding (person+motorcycle) model...")
    triple_weights = train_model(
        yaml_path  = triple_yaml,
        model_name = "triple_train",
        epochs     = 50,
    )
    validate_model(triple_weights, triple_yaml)

    # Step 5 — Train license plate detector
    print("\n[5/5] Training license plate detector...")
    plate_weights = train_model(
        yaml_path  = plate_yaml,
        model_name = "plate_train",
        epochs     = 40,
        img_size   = 640,
    )
    validate_model(plate_weights, plate_yaml)

    # Organise final weights
    print("\n[DONE] Organising model weights...")
    merge_weights({
        "helmet":   helmet_weights,
        "seatbelt": seatbelt_weights,
        "triple":   triple_weights,
        "plate":    plate_weights,
    })

    print("\n✓ All models trained. Update config.py paths and run app.py")