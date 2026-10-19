"""Inspect, validate and split the calamansi leaf dataset.

The original files are never moved, copied or deleted. Instead this script
writes a manifest (outputs/splits.csv) that train_model.py and
evaluate_model.py read, plus a JSON report (outputs/dataset_report.json).

What it checks:
  * folder layout (split/class/ or class/ directly) and class names
  * unreadable / unsupported / tiny images (excluded, reported)
  * exact duplicates (MD5) and near-duplicates (burst shots of the same leaf:
    camera timestamps <= 30 s apart with a similar leaf crop, or a
    near-identical whole image)
  * Roboflow "_aug" copies, which are augmented versions of another photo
  * class balance and background colour per class (shortcut-learning risk)

Splitting: images are grouped so that a photo, its Roboflow augmented copy
and any (near-)duplicates always land in the same split, then groups are
assigned to train/val/test with a stratified 70/15/15 ratio.

Usage:
    python prepare_dataset.py                 # re-split 70/15/15 (default)
    python prepare_dataset.py --use-existing-split
    python prepare_dataset.py --include-roboflow-aug
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from config import (
    BACKEND_DIR,
    ALLOWED_EXTENSIONS,
    CLASS_NAMES,
    DATASET_DIR,
    DATASET_REPORT,
    SEED,
    SPLIT_NAMES,
    SPLITS_CSV,
    normalize_class,
)

MIN_SIDE = 32
EXCLUSIONS_CSV = BACKEND_DIR / "dataset_exclusions.csv"  # written by check_external_duplicates.py
# Thresholds calibrated by visually inspecting pairs from this dataset. A plain
# whole-image hash does not work here: the uniform blue backdrop dominates it
# and makes unrelated leaves look identical.
BURST_SECONDS = 30
BURST_CROP_SIM = 0.93      # leaf-crop similarity for photos taken seconds apart
IDENTICAL_SIM = 0.995      # whole-image similarity for any pair (no timestamp needed)
TIMESTAMP = re.compile(r"(?:IMG_?)?(20\d{6})_?(\d{6})")
RF_STEM = re.compile(r"^(.*?)(?:_(?:jpg|jpeg|png))?\.rf\.[0-9a-f]+(_aug)?$", re.IGNORECASE)


def discover(root: Path) -> list[dict]:
    """Find images under root/<split>/<class>/ or root/<class>/."""
    records = []
    for split_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        split = SPLIT_NAMES.get(split_dir.name.lower())
        if split is None and normalize_class(split_dir.name):
            class_dirs, split = [split_dir], None  # class folder at top level
        elif split is not None:
            class_dirs = [p for p in split_dir.iterdir() if p.is_dir()]
        else:
            continue
        for class_dir in class_dirs:
            label = normalize_class(class_dir.name)
            if label is None:
                print(f"  ! ignoring unknown class folder: {class_dir}")
                continue
            for f in sorted(class_dir.iterdir()):
                if f.is_file():
                    records.append({"path": f, "label": label, "original_split": split})
    return records


def source_stem(path: Path) -> tuple[str, bool]:
    """'IMG123_jpg.rf.<hash>_aug.jpg' -> ('IMG123', True)."""
    m = RF_STEM.match(path.stem)
    if m:
        return m.group(1), bool(m.group(2))
    return path.stem, False


def capture_time(stem: str) -> float | None:
    """Seconds since epoch parsed from camera names like IMG20220404223945 / IMG_20220405_091954."""
    m = TIMESTAMP.match(stem)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
    except ValueError:
        return None


def _unit(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.float32).flatten()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6)


def similarity_features(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """(whole-image vector, leaf-crop vector), both 32x32 RGB, zero-mean, unit-norm.

    The leaf crop is the bounding box of pixels that differ from the median
    border colour, so the backdrop does not dominate the comparison.
    """
    a = np.asarray(img.convert("RGB").resize((128, 128)), dtype=np.float32)
    frame = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3),
                            a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    mask = np.linalg.norm(a - np.median(frame, axis=0), axis=2) > 50
    ys, xs = np.nonzero(mask)
    box = (0, 0, 128, 128) if len(ys) < 20 else (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    whole = Image.fromarray(a.astype(np.uint8))
    return _unit(np.asarray(whole.resize((32, 32)))), _unit(np.asarray(whole.crop(box).resize((32, 32))))


def border_rgb(img: Image.Image) -> list[float]:
    """Mean RGB of a 10% frame around the image (approximates the background)."""
    a = np.asarray(img.convert("RGB").resize((100, 100)), dtype=np.float32)
    frame = np.concatenate([a[:10].reshape(-1, 3), a[-10:].reshape(-1, 3),
                            a[:, :10].reshape(-1, 3), a[:, -10:].reshape(-1, 3)])
    return frame.mean(axis=0).round(1).tolist()


def background_kind(rgb: list[float]) -> str:
    r, g, b = rgb
    if b > r + 40 and b > g + 20:
        return "blue"
    if min(rgb) > 150 and max(rgb) - min(rgb) < 40:
        return "white/grey"
    return "other"


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def stratified_group_split(groups: dict[int, list[dict]], ratios=(0.70, 0.15, 0.15)) -> dict[int, str]:
    """Assign whole groups to splits, per class, hitting the ratios by image count."""
    rng = random.Random(SEED)
    assignment: dict[int, str] = {}
    by_class: dict[str, list[int]] = defaultdict(list)
    for gid, members in groups.items():
        by_class[members[0]["label"]].append(gid)
    for label, gids in by_class.items():
        rng.shuffle(gids)
        total = sum(len(groups[g]) for g in gids)
        targets = {"val": round(total * ratios[1]), "test": round(total * ratios[2])}
        filled = {"val": 0, "test": 0}
        for gid in gids:
            size = len(groups[gid])
            # Fill test, then val, with groups that fit; everything else is train.
            for split in ("test", "val"):
                if filled[split] + size <= targets[split]:
                    assignment[gid] = split
                    filled[split] += size
                    break
            else:
                assignment[gid] = "train"
    return assignment


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--use-existing-split", action="store_true",
                    help="keep the train/valid/test folders as delivered instead of re-splitting 70/15/15")
    ap.add_argument("--keep-excluded", action="store_true",
                    help="ignore dataset_exclusions.csv (keeps images that were found to be copies of a public non-calamansi dataset)")
    ap.add_argument("--include-roboflow-aug", action="store_true",
                    help="keep Roboflow '_aug' copies in the training split (never in val/test)")
    args = ap.parse_args()

    print(f"Dataset directory: {DATASET_DIR}")
    records = discover(DATASET_DIR)
    excluded = []
    if EXCLUSIONS_CSV.exists() and not args.keep_excluded:
        with open(EXCLUSIONS_CSV, encoding="utf-8") as f:
            skip = {r["filepath"]: r for r in csv.DictReader(f)}
        rel = lambda r: str(r["path"].relative_to(DATASET_DIR)).replace("\\", "/")  # noqa: E731
        excluded = [skip[rel(r)] for r in records if rel(r) in skip]
        records = [r for r in records if rel(r) not in skip]
        print(f"Excluded {len(excluded)} files listed in {EXCLUSIONS_CSV.name} "
              f"(copies of a public non-calamansi dataset; see check_external_duplicates.py)")
    if not records:
        raise SystemExit(
            f"No images found. Expected {DATASET_DIR}/<train|valid|test>/<healthy|damaged>/ "
            "or <healthy|damaged>/ folders. Set DATASET_DIR in backend/.env if the dataset is elsewhere."
        )

    layout = Counter((r["original_split"], r["label"]) for r in records)
    print("Folder layout (files):")
    for (split, label), n in sorted(layout.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        print(f"  {split or '-':6s} {label:8s} {n}")

    # ---- validate every file -------------------------------------------------
    valid, problems = [], []
    for r in records:
        p: Path = r["path"]
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            problems.append({"file": str(p), "issue": "unsupported extension"})
            continue
        try:
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im:
                im.load()
                if min(im.size) < MIN_SIDE:
                    problems.append({"file": str(p), "issue": f"too small {im.size}"})
                    continue
                whole_vec, crop_vec = similarity_features(im)
                r.update(width=im.width, height=im.height, mode=im.mode,
                         whole_vec=whole_vec, crop_vec=crop_vec, border=border_rgb(im))
        except (UnidentifiedImageError, OSError, SyntaxError) as e:
            problems.append({"file": str(p), "issue": f"unreadable: {e}"})
            continue
        r["md5"] = hashlib.md5(p.read_bytes()).hexdigest()
        r["stem"], r["is_rf_aug"] = source_stem(p)
        r["time"] = capture_time(r["stem"])
        valid.append(r)
    print(f"Readable images: {len(valid)} / {len(records)}  (problems: {len(problems)})")

    # ---- group duplicates ----------------------------------------------------
    n = len(valid)
    uf = UnionFind(n)
    first_by_key: dict[tuple, int] = {}
    for i, r in enumerate(valid):
        for key in (("md5", r["md5"]), ("stem", r["stem"])):
            if key in first_by_key:
                uf.union(i, first_by_key[key])
            else:
                first_by_key[key] = i
    md5_counts = Counter(r["md5"] for r in valid)
    exact_dups = [h for h, c in md5_counts.items() if c > 1]

    whole = np.stack([r["whole_vec"] for r in valid])
    crop = np.stack([r["crop_vec"] for r in valid])
    times = np.array([r["time"] if r["time"] is not None else np.nan for r in valid])
    whole_sim, crop_sim = whole @ whole.T, crop @ crop.T
    near_pairs, cross_label_pairs = [], []
    for i in range(n):
        for j in range(i + 1, n):
            if valid[i]["stem"] == valid[j]["stem"]:
                continue
            burst = abs(times[i] - times[j]) <= BURST_SECONDS and crop_sim[i, j] >= BURST_CROP_SIM
            if burst or whole_sim[i, j] >= IDENTICAL_SIM:
                pair = (i, j, round(float(max(crop_sim[i, j], whole_sim[i, j])), 4))
                if valid[i]["label"] == valid[j]["label"]:
                    near_pairs.append(pair)
                    uf.union(i, j)
                else:
                    # Similar-looking photos with different labels: usually two different
                    # leaves shot seconds apart, occasionally a labelling mistake. Not
                    # merged (that would chain unrelated photos); listed for manual review.
                    cross_label_pairs.append(pair)

    groups: dict[int, list[dict]] = defaultdict(list)
    for i, r in enumerate(valid):
        groups[uf.find(i)].append(r)

    conflicts = []
    for gid, members in list(groups.items()):
        if len({m["label"] for m in members}) > 1:
            conflicts.append([f"{m['path'].relative_to(DATASET_DIR)} ({m['label']})" for m in members])
            del groups[gid]  # same/near-identical image with two labels: exclude, report as possible mislabel
    excluded_conflict = sum(len(c) for c in conflicts)

    # ---- choose splits -------------------------------------------------------
    if args.use_existing_split:
        assignment = {}
        for gid, members in groups.items():
            splits = Counter(m["original_split"] or "train" for m in members)
            assignment[gid] = splits.most_common(1)[0][0]
    else:
        # Size groups by their non-augmented members so ratios reflect real photos.
        real_groups = {gid: [m for m in ms if not m["is_rf_aug"]] or ms for gid, ms in groups.items()}
        assignment = stratified_group_split(real_groups)

    rows = []
    for gid, members in groups.items():
        split = assignment[gid]
        for m in members:
            if m["is_rf_aug"] and (split != "train" or not args.include_roboflow_aug):
                continue  # augmented copies never enter val/test; excluded from train unless asked
            rows.append({"filepath": str(m["path"].relative_to(DATASET_DIR)).replace("\\", "/"),
                         "label": m["label"], "split": split, "group": gid,
                         "original_split": m["original_split"] or ""})

    rows.sort(key=lambda r: (r["split"], r["label"], r["filepath"]))
    with open(SPLITS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- report --------------------------------------------------------------
    split_counts = {s: dict(Counter(r["label"] for r in rows if r["split"] == s)) for s in ("train", "val", "test")}
    unique_photos = Counter(m["label"] for ms in groups.values() for m in ms if not m["is_rf_aug"])
    rf_aug = Counter(m["label"] for ms in groups.values() for m in ms if m["is_rf_aug"])
    bg = defaultdict(Counter)
    for r in valid:
        if not r["is_rf_aug"]:
            bg[r["label"]][background_kind(r["border"])] += 1
    sizes = Counter(f"{r['width']}x{r['height']}" for r in valid)
    majority, minority = max(unique_photos.values()), min(unique_photos.values())

    leaky_groups = sum(1 for ms in groups.values() if len({m["original_split"] for m in ms}) > 1)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_dir": str(DATASET_DIR),
        "folder_layout": {f"{s or '-'}/{l}": c for (s, l), c in sorted(layout.items(), key=str)},
        "files_found": len(records) + len(excluded),
        "excluded_non_calamansi": {"count": len(excluded), "list": str(EXCLUSIONS_CSV.name),
                                   "reason": "pixel-identical copies of the public Citrus Leaves dataset (Mendeley 3f83gxmv57)"},
        "readable_images": len(valid),
        "problem_files": problems,
        "roboflow_aug_copies": dict(rf_aug),
        "unique_source_photos": dict(unique_photos),
        "imbalance_ratio": round(majority / minority, 2) if minority else None,
        "exact_duplicate_hashes": len(exact_dups),
        "near_duplicate_pairs": [
            {"a": str(valid[i]["path"].relative_to(DATASET_DIR)), "b": str(valid[j]["path"].relative_to(DATASET_DIR)),
             "similarity": d} for i, j, d in near_pairs],
        "groups_spanning_original_splits": leaky_groups,
        "possible_mislabels_review": [
            {"a": f"{valid[i]['path'].relative_to(DATASET_DIR)} ({valid[i]['label']})",
             "b": f"{valid[j]['path'].relative_to(DATASET_DIR)} ({valid[j]['label']})", "similarity": d}
            for i, j, d in cross_label_pairs],
        "label_conflicts_excluded": conflicts,
        "excluded_due_to_conflict": excluded_conflict,
        "image_sizes": dict(sizes.most_common(5)),
        "background_by_class": {k: dict(v) for k, v in bg.items()},
        "split_strategy": "existing folders" if args.use_existing_split else "stratified group split 70/15/15 (seed 42)",
        "include_roboflow_aug_in_train": args.include_roboflow_aug,
        "split_counts": split_counts,
    }
    DATASET_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Roboflow '_aug' copies: {dict(rf_aug)} -> {'kept in train only' if args.include_roboflow_aug else 'excluded'}")
    print(f"Unique source photos: {dict(unique_photos)} (imbalance {report['imbalance_ratio']}:1)")
    print(f"Exact duplicates: {len(exact_dups)} | near-duplicate pairs: {len(near_pairs)} | label conflicts: {len(conflicts)}")
    print(f"Similar photos with different labels (review in report): {len(cross_label_pairs)}")
    print(f"Duplicate groups spanning the ORIGINAL train/valid/test folders (leakage): {leaky_groups}")
    print(f"Image sizes: {report['image_sizes']}")
    print(f"Background (border colour) by class: {report['background_by_class']}")
    print(f"Split counts: {split_counts}")
    print(f"Wrote {SPLITS_CSV}\nWrote {DATASET_REPORT}")
    for cls in CLASS_NAMES:
        if unique_photos.get(cls, 0) < 100:
            print(f"WARNING: only {unique_photos.get(cls, 0)} '{cls}' photos; results will be unreliable.")


if __name__ == "__main__":
    main()
