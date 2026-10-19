"""Species test of the calamansi-leaf check: does it reject other citrus and accept calamansi?

Runs every image through the exact app pipeline (predict.Predictor: leaf check, region
analysis, Healthy/Damaged classifier) and records the whole-photo score of each check.

Test sets (none of them used for training or for choosing thresholds):
  regression        the lemon-leaf photo that was wrongly accepted (regression_cases/)
  calamansi_*       held-out calamansi test photos (Healthy / Damaged), sharp and blurred
  lemon_leaves      held-out lemon leaves (two Mendeley datasets, test groups only), sharp and blurred
  orange_leaves_hlb held-out orange leaves (Mexico HLB dataset, test groups only)
  inat_<species>    real photos from iNaturalist (download_inat.py), held-out TEST split only
                    (train_gate.split_of, one group per observation): lemon, limes, orange, and
                    calamansi split into "leaves visible" / "no clear leaves" by the manual labels
                    in ood_data/inat/calamansi_labels.csv (photos without clear leaves are never
                    used in training, so all of them are tested)
  realworld         backend/realworld_test (branch with fruit, fruit only, screenshot, ...)

Writes outputs/species_evaluation_<tag>.csv (per image) and .json (summary).
Usage:  python evaluate_species.py --tag before|after
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from config import BACKEND_DIR, DATASET_DIR, OUTPUTS_DIR, SEED, SPLITS_CSV
from diagnose_dataset import stage_scores
from download_ood_data import OOD_DIR
from predict import Predictor, load_image, pad_to_square
from train_gate import negative_sources, split_of

INAT = OOD_DIR / "inat"
EXPECT = {"accept": "accept", "reject": "reject"}


def cases() -> list[dict]:
    out = []

    def add(group, path, expected, label=None, blur=0):
        out.append({"group": group, "path": path, "expected": expected, "label": label, "blur": blur})

    for p in sorted((BACKEND_DIR / "regression_cases").glob("*")):
        add("regression_lemon_upload", p, "reject")
    rows = [r for r in csv.DictReader(open(SPLITS_CSV, encoding="utf-8")) if r["split"] == "test"]
    for r in rows:
        add(f"calamansi_{r['label'].lower()}", DATASET_DIR / r["filepath"], "accept", r["label"])
    rng = random.Random(SEED)
    for r in rng.sample(rows, 40):  # too blurry to verify: rejecting is acceptable, a wrong label is not
        add("calamansi_blurred", DATASET_DIR / r["filepath"], "either", r["label"], blur=4)
    negs = negative_sources(random.Random(SEED))
    for cat in ("lemon_leaves", "orange_leaves_hlb"):
        test = [p for p, g in negs.get(cat, []) if split_of(f"{cat}/{g}") == "test"]
        for p in test:
            add(cat, p, "reject")
        for p in rng.sample(test, min(40, len(test))):
            add(f"{cat}_blurred", p, "reject", blur=4)
    labels = {}
    lab_file = INAT / "calamansi_labels.csv"
    if lab_file.exists():
        labels = {r["file"]: r["leaves"] for r in csv.DictReader(open(lab_file, encoding="utf-8"))}
    for sp in sorted(d.name for d in INAT.iterdir() if d.is_dir()) if INAT.exists() else []:
        for p in sorted((INAT / sp).glob("*.jpg")):
            if sp == "calamansi":
                lab = labels.get(f"calamansi/{p.name}")
                if lab is None:
                    continue  # not reviewed
                if lab == "yes" and split_of(f"inat_calamansi/{p.stem}") != "test":
                    continue  # used for training / threshold selection
                add("inat_calamansi_leaves_visible" if lab == "yes" else "inat_calamansi_no_clear_leaves", p,
                    "accept" if lab == "yes" else "either")
            elif split_of(f"inat_other_citrus/{sp}/{p.stem}") == "test":
                add(f"inat_{sp}", p, "reject")
    for p in sorted((BACKEND_DIR / "realworld_test").rglob("*")):
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            cat = p.parent.name
            add(f"realworld_{cat}", p, "accept" if cat in ("leaf_healthy", "leaf_damaged", "plant_unlabeled") else "reject")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    P = Predictor()
    rows = []
    for c in cases():
        img = ImageOps.exif_transpose(Image.open(c["path"])).convert("RGB")
        if c["blur"]:
            img = img.filter(ImageFilter.GaussianBlur(c["blur"] * max(img.size) / 640))
        arr = np.asarray(pad_to_square(img).resize((224, 224), Image.BILINEAR))
        lin, nov, cnn = stage_scores(P.gate, arr)
        r = P.predict_image(img)
        ok = c["expected"] == "either" or (r.accepted == (c["expected"] == "accept") and
                                           (not r.accepted or c["label"] is None or r.predicted_class == c["label"]))
        rows.append({"group": c["group"], "image": str(c["path"].relative_to(BACKEND_DIR.parent)) if BACKEND_DIR.parent in c["path"].parents else str(c["path"]),
                     "blur": c["blur"], "expected": c["expected"], "true_label": c["label"] or "",
                     "accepted": r.accepted, "predicted_class": r.predicted_class or "",
                     "health_confidence": round(r.confidence, 4) if r.confidence is not None else "",
                     "check_linear": round(lin, 4), "check_novelty": round(nov, 3), "check_cnn": round(cnn, 4),
                     "analysis": r.analysis, "regions": f"{r.regions_used}/{r.regions_checked}",
                     "rejection_reason": r.gate.reason or "", "correct": ok})
    out = OUTPUTS_DIR / f"species_evaluation_{args.tag}"
    with open(f"{out}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = defaultdict(list)
    for r in rows:
        by[r["group"]].append(r)
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "thresholds": {
        "linear": P.gate.t_prob, "novelty": P.gate.t_dist, "cnn": P.gate.t_cnn}, "groups": {}}
    print(f"{'group':36s} {'n':>4s} {'expected':>8s} {'accepted':>9s} {'correct':>8s}")
    for g, rs in by.items():
        acc = sum(r["accepted"] for r in rs) / len(rs)
        cor = sum(r["correct"] for r in rs) / len(rs)
        summary["groups"][g] = {"n": len(rs), "expected": rs[0]["expected"], "accepted": round(acc, 4), "correct": round(cor, 4)}
        print(f"{g:36s} {len(rs):4d} {rs[0]['expected']:>8s} {acc:9.1%} {cor:8.1%}")
    json.dump(summary, open(f"{out}.json", "w"), indent=2)
    print(f"Wrote {out}.csv/.json")


if __name__ == "__main__":
    main()
