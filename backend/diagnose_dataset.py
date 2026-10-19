"""Diagnostic: run every image of the original dataset folders through the exact
pipeline the backend uses (predict.Predictor: leaf check, region analysis,
Healthy/Damaged classifier) and record why each image is accepted or rejected.

Each image is also tagged with how it was used in training:
  * split in outputs/splits.csv (train / val / test) -> a genuine calamansi photo
  * listed in dataset_exclusions.csv -> copy of the public Citrus Leaves dataset,
    excluded from training and used as a "not calamansi" example
  * Roboflow "_aug" copy -> not used (augmented duplicate of another photo)

Writes outputs/dataset_diagnostic.csv and prints a summary.
Usage:  python diagnose_dataset.py [folder ...]     (default: train valid test)
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict

from config import BACKEND_DIR, DATASET_DIR, OUTPUTS_DIR, normalize_class
import numpy as np

from predict import Predictor, load_image

EXCLUSIONS = BACKEND_DIR / "dataset_exclusions.csv"


def stage_scores(gate, arr: np.ndarray) -> tuple[float, float, float]:
    """Whole-photo scores of the three checks: linear probability, novelty distance, CNN score."""
    x = arr[np.newaxis].astype(np.float32)
    f = gate.extractor.predict(x, verbose=0)
    f = f / np.linalg.norm(f, axis=1, keepdims=True)
    lin = float(1 / (1 + np.exp(-(f @ gate.coef + gate.intercept)))[0])
    z = (f - gate.pca_mean) @ gate.pca_components.T
    nov = float(np.sqrt(((gate.bank - z) ** 2).sum(-1).min()))
    return lin, nov, float(gate.cnn.predict(x, verbose=0).ravel()[0])


def main() -> None:
    folders = sys.argv[1:] or ["train", "valid", "test"]
    splits = {r["filepath"]: r["split"] for r in csv.DictReader(open(OUTPUTS_DIR / "splits.csv", encoding="utf-8"))}
    excluded = {r["filepath"]: r["matches"] for r in csv.DictReader(open(EXCLUSIONS, encoding="utf-8"))} if EXCLUSIONS.exists() else {}
    P = Predictor()
    print(f"Classifier {P.version}; leaf-check thresholds: linear>={P.gate.t_prob:.3f}, "
          f"novelty<={P.gate.t_dist:.2f}, cnn>={P.gate.t_cnn:.3f}")
    rows = []
    for folder in folders:
        for cls_dir in sorted((DATASET_DIR / folder).iterdir()):
            label = normalize_class(cls_dir.name) if cls_dir.is_dir() else None
            if not label:
                continue
            for f in sorted(cls_dir.glob("*.jpg")):
                rel = f"{folder}/{cls_dir.name}/{f.name}"
                usage = ("excluded: public citrus copy" if rel in excluded else
                         "roboflow _aug copy (unused)" if "_aug" in f.stem else
                         f"calamansi photo ({splits[rel]} split)" if rel in splits else "not in manifest")
                r = P.predict_file(f)
                lin, nov, cnn = stage_scores(P.gate, load_image(f))
                failed = [n for n, bad in (("linear", lin < P.gate.t_prob), ("novelty", nov > P.gate.t_dist),
                                           ("cnn", cnn < P.gate.t_cnn)) if bad]
                rows.append({"image": rel, "folder_label": label, "training_use": usage,
                             "accepted": r.accepted, "predicted_class": r.predicted_class or "",
                             "confidence": round(r.confidence, 4) if r.confidence is not None else "",
                             "p_healthy": round(r.probabilities.get("Healthy", 0), 4) if r.probabilities else "",
                             "whole_linear": round(lin, 4), "whole_novelty": round(nov, 3), "whole_cnn": round(cnn, 4),
                             "whole_photo_failed": "+".join(failed),
                             "analysis": r.analysis, "regions_used": f"{r.regions_used}/{r.regions_checked}", "rejection_reason": r.gate.reason or "",
                             "matches_public_file": excluded.get(rel, "")})
        print(f"  {folder}: done", flush=True)

    out = OUTPUTS_DIR / "dataset_diagnostic.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    groups = defaultdict(list)
    for r in rows:
        groups[(r["image"].split("/")[0] + "/" + r["folder_label"], r["training_use"].split(" (")[0])].append(r)
    print(f"\n{'folder':16s} {'training use':30s} {'n':>4s} {'accepted':>9s} {'correct class':>14s}  rejection reasons")
    for (folder, use), rs in sorted(groups.items()):
        acc = [r for r in rs if r["accepted"]]
        correct = sum(r["predicted_class"] == r["folder_label"] for r in acc)
        reasons = Counter(r["rejection_reason"] for r in rs if not r["accepted"])
        print(f"{folder:16s} {use:30s} {len(rs):4d} {len(acc):9d} {correct:14d}  {dict(reasons) if reasons else ''}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
