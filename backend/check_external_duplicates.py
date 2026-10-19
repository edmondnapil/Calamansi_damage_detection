"""Find dataset images that are copies of images from a public dataset.

Background: all 150 white-background "damaged" photos in the calamansi dataset
(files named b--NNN-_png... and NN-p_png...) turned out to be pixel-identical
copies of the public "Citrus Leaves" dataset (Rauf et al., 2019, Mendeley Data
3f83gxmv57), which shows orange/citrus leaves from Pakistan, not calamansi.

This script compares every image in the calamansi dataset with a reference
folder and writes the matches to backend/dataset_exclusions.csv, which
prepare_dataset.py then leaves out of training and evaluation. The original
files are not touched.

Usage:
    python download_ood_data.py citrus_leaves
    python check_external_duplicates.py                    # uses ood_data/citrus_leaves
    python check_external_duplicates.py <reference folder>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from config import ALLOWED_EXTENSIONS, BACKEND_DIR, DATASET_DIR
from download_ood_data import OOD_DIR

EXCLUSIONS_CSV = BACKEND_DIR / "dataset_exclusions.csv"
MATCH_THRESHOLD = 0.98  # correlation of 48x48 greyscale thumbnails (1.0 = identical)


def thumb(path: Path, mirror: bool = False) -> np.ndarray:
    img = Image.open(path).convert("L").resize((48, 48))
    if mirror:
        img = ImageOps.mirror(img)
    v = np.asarray(img, dtype=np.float32).ravel()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6)


def main() -> None:
    reference = Path(sys.argv[1]) if len(sys.argv) > 1 else OOD_DIR / "citrus_leaves" / "files"
    if not reference.exists():
        raise SystemExit(f"Reference folder not found: {reference}. Run `python download_ood_data.py citrus_leaves`.")
    ours = sorted(p for split in ("train", "valid", "val", "test") for p in (DATASET_DIR / split).rglob("*")
                  if p.suffix.lower() in ALLOWED_EXTENSIONS and "_aug" not in p.stem)
    ours += sorted(p for p in DATASET_DIR.glob("*/*") if p.parent.name.lower() in ("healthy", "damaged")
                   and p.suffix.lower() in ALLOWED_EXTENSIONS and "_aug" not in p.stem)
    refs = sorted(p for p in reference.rglob("*") if p.suffix.lower() in ALLOWED_EXTENSIONS | {".png"})
    print(f"Comparing {len(ours)} dataset images with {len(refs)} reference images...")

    a = np.stack([thumb(p) for p in ours])
    b = np.stack([thumb(p) for p in refs] + [thumb(p, mirror=True) for p in refs])
    sim = a @ b.T
    best, idx = sim.max(1), sim.argmax(1)

    rows = [{"filepath": str(p.relative_to(DATASET_DIR)).replace("\\", "/"),
             "reason": "copy of public Citrus Leaves dataset (not calamansi)",
             "matches": "/".join(refs[idx[i] % len(refs)].relative_to(reference).parts),
             "similarity": round(float(best[i]), 4)}
            for i, p in enumerate(ours) if best[i] >= MATCH_THRESHOLD]
    with open(EXCLUSIONS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filepath", "reason", "matches", "similarity"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} dataset images match the reference set (similarity >= {MATCH_THRESHOLD}).")
    print(f"Wrote {EXCLUSIONS_CSV}. Re-run prepare_dataset.py, train_model.py and evaluate_model.py.")


if __name__ == "__main__":
    main()
