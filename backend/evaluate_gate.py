"""Evaluate the saved calamansi-leaf check end to end, exactly as the web app runs it
(whole photo first, then leaf regions; then the Healthy/Damaged classifier).

All images come from the held-out TEST splits, which were never used for
training or for choosing thresholds:
  * calamansi test photos, the same leaves on new backgrounds, branch-like
    clusters of test leaves
  * every negative category (other citrus, fruit, plants, flowers, objects,
    people) and blank / noise backgrounds

Writes outputs/gate_evaluation.json (shown on the Settings page).
Usage:  python evaluate_gate.py
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from composites import augment, leaf_mask, random_background
from config import CLASS_NAMES, DATASET_DIR, OUTPUTS_DIR, SEED, SPLITS_CSV
from predict import InvalidImageError, Predictor, load_image
from train_gate import negative_sources, remove_leaf, split_of
from train_model import background_variants


def main() -> None:
    P = Predictor()
    rows = [r for r in csv.DictReader(open(SPLITS_CSV, encoding="utf-8")) if r["split"] == "test"]
    labels = np.array([CLASS_NAMES.index(r["label"]) for r in rows], dtype=np.float32)
    photos = np.stack([load_image(DATASET_DIR / r["filepath"]) for r in rows])

    def run(imgs) -> list:
        return [P.predict_image(Image.fromarray(a) if isinstance(a, np.ndarray) else a) for a in imgs]

    print("Calamansi test photos...", flush=True)
    res = [P.predict_file(DATASET_DIR / r["filepath"]) for r in rows]
    accepted = np.array([x.accepted for x in res])
    correct = np.array([x.accepted and x.predicted_class == r["label"] for x, r in zip(res, rows)])
    variants, vlabels = background_variants(photos, labels, 2, 200, SEED + 2, "test")
    n_single = len(variants) - 200
    vres = run(variants)
    vacc = np.array([x.accepted for x in vres])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "end-to-end app pipeline: stage 1 (logistic regression + novelty on ImageNet MobileNetV2 features) "
                  "and stage 2 (fine-tuned MobileNetV2) on the whole photo, then on leaf regions",
        "calamansi_test_acceptance": {
            "all_photos": round(float(accepted.mean()), 4),
            **{c: round(float(accepted[labels == i].mean()), 4) for i, c in enumerate(CLASS_NAMES)},
            "n": int(len(rows)),
            "accepted_and_correctly_classified": round(float(correct.mean()), 4),
            "on_new_backgrounds": round(float(vacc[:n_single].mean()), 4),
            "n_new_backgrounds": int(n_single),
            "branch_like_clusters": round(float(vacc[n_single:].mean()), 4),
            "n_branch_like_clusters": 200,
        },
        "negative_test_rejection": {},
    }

    negs = negative_sources(random.Random(SEED))
    for cat, items in negs.items():
        paths = [p for p, g in items if split_of(f"{cat}/{g}") == "test"]
        print(f"{cat}: {len(paths)} test images...", flush=True)
        out = []
        for p in paths:
            try:
                out.append(P.predict_file(p))
            except InvalidImageError:
                pass
        report["negative_test_rejection"][cat] = {
            "rejected": round(1 - sum(x.accepted for x in out) / len(out), 4), "n": len(out),
            "accepted_via_regions": sum(x.accepted and x.analysis == "leaf_regions" for x in out)}

    # Blank backgrounds from the held-out test photos (leaf painted out) and synthetic surfaces.
    r = random.Random(SEED + 22)
    blanks = []
    for row in rows[:80]:
        arr = load_image(DATASET_DIR / row["filepath"])
        m = leaf_mask(arr)
        if m is not None:
            blanks.append(np.asarray(augment(Image.fromarray(remove_leaf(arr, m, r.randint(0, 1 << 30))), r)))
    blanks += [np.asarray(augment(random_background(r, []), r)) for _ in range(150)]
    rng = np.random.default_rng(SEED)
    blanks += [rng.integers(0, 255, (224, 224, 3), dtype=np.uint8) for _ in range(40)]
    bres = run(blanks)
    report["negative_test_rejection"]["empty_backgrounds"] = {
        "rejected": round(1 - sum(x.accepted for x in bres) / len(bres), 4), "n": len(bres), "accepted_via_regions": 0}

    (OUTPUTS_DIR / "gate_evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nCalamansi:", report["calamansi_test_acceptance"])
    for c, v in report["negative_test_rejection"].items():
        print(f"  {c:34s} rejected {v['rejected']:.3f}  (n={v['n']}, accepted via regions: {v['accepted_via_regions']})")
    print("Wrote outputs/gate_evaluation.json")


if __name__ == "__main__":
    main()
