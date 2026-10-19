"""Choose the app's blur and region settings for the calamansi-leaf check on VALIDATION data only,
and write them to models/leaf_gate_config.json (read by predict.CombinedGate).

  min_sharpness       a quarter of the 1st percentile of the sharpness of validation calamansi
                      photos (dataset validation split + real iNaturalist calamansi photos):
                      every sharp validation photo passes with a wide margin, 2-4 px blur fails.
  min_region_fraction when a photo is not accepted as a whole, the share of its regions that must
                      pass. Chosen as the lowest share seen among validation calamansi photos that
                      region analysis accepts (rounded down), i.e. none of them is lost; any
                      validation negative accepted with a smaller share is then rejected.

Validation data: real calamansi photos from iNaturalist (leaves clearly visible, train + val splits:
neither check was trained on them), lemon/orange leaves (val split), iNaturalist lemon/lime/orange
photos (train + val splits). The test splits are never looked at here.
Usage:  python calibrate_gate.py
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timezone

import numpy as np

from config import DATASET_DIR, MODELS_DIR, SEED, SPLITS_CSV
from predict import GATE_CONFIG_PATH, Predictor, leaf_regions, open_image, sharpness
from train_gate import inat_calamansi, negative_sources, split_of


def region_share(P: Predictor, img) -> tuple[bool, float | None]:
    """(accepted as a whole, share of regions accepted or None if not looked at)."""
    whole = P.predict_image(img)
    if whole.accepted and whole.analysis == "whole_photo":
        return True, None
    found = leaf_regions(img, P.img_size)
    if not found:
        return False, None
    checks = P.gate.check_batch(np.stack(found))
    ok = sum(c.is_calamansi_leaf for c in checks)
    return False, (ok / len(found)) if ok >= 2 else 0.0


def main() -> None:
    P = Predictor()
    P.gate.t_sharp, P.gate.min_region_fraction = 0.0, 0.0  # measure without the settings being chosen

    rows = [r for r in csv.DictReader(open(SPLITS_CSV, encoding="utf-8")) if r["split"] == "val"]
    cal_val = [p for p, sp in inat_calamansi() if sp in ("train", "val")]
    val_sharp = [sharpness(open_image(DATASET_DIR / r["filepath"])) for r in rows] + \
                [sharpness(open_image(p)) for p, sp in inat_calamansi() if sp == "val"]
    min_sharp = 0.25 * float(np.percentile(val_sharp, 1))

    negs = negative_sources(random.Random(SEED))
    neg_val = [p for c in ("lemon_leaves", "orange_leaves_hlb") for p, g in negs[c] if split_of(f"{c}/{g}") == "val"]
    neg_val += [p for p, g in negs["inat_other_citrus"] if split_of(f"inat_other_citrus/{g}") in ("train", "val")]

    pos_shares, neg_shares, pos_whole, neg_whole = [], [], 0, 0
    for p in cal_val:
        w, sh = region_share(P, open_image(p))
        pos_whole += w
        if sh:
            pos_shares.append(sh)
    for p in neg_val:
        w, sh = region_share(P, open_image(p))
        neg_whole += w
        if sh:
            neg_shares.append(sh)
    fraction = math.floor(min(pos_shares) * 20) / 20 if pos_shares else 0.0
    cfg = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "min_sharpness": round(min_sharp, 3),
        "min_region_fraction": fraction,
        "chosen_on": {
            "calamansi_validation_photos": len(cal_val) + len(rows),
            "real_calamansi_accepted_whole": pos_whole, "real_calamansi_accepted_via_regions": len(pos_shares),
            "real_calamansi_region_shares": sorted(round(x, 3) for x in pos_shares),
            "negatives": len(neg_val), "negatives_accepted_whole": neg_whole,
            "negatives_accepted_via_regions_before": len(neg_shares),
            "negatives_accepted_via_regions_after": sum(x >= fraction for x in neg_shares),
            "sharpness_validation_1st_percentile": round(float(np.percentile(val_sharp, 1)), 2),
        },
    }
    GATE_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    main()
