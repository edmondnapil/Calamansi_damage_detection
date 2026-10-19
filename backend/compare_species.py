"""Side-by-side table of species evaluations (outputs/species_evaluation_<tag>.csv) on the SAME images.

Earlier runs tested every iNaturalist photo; later ones only the held-out test split (the rest is
used for training). This script keeps only images present in every run, so the columns compare
like with like. Usage:  python compare_species.py before after1 after2
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict

from config import OUTPUTS_DIR


def main() -> None:
    tags = sys.argv[1:]
    runs = {t: {(r["group"], r["image"], r["blur"]): r for r in csv.DictReader(open(OUTPUTS_DIR / f"species_evaluation_{t}.csv", encoding="utf-8"))}
            for t in tags}
    common = set.intersection(*(set(r) for r in runs.values()))
    groups = defaultdict(list)
    for key in common:
        groups[key[0]].append(key)
    print(f"{'group':34s} {'n':>4s} {'expect':>7s} " + " ".join(f"{t + ' acc':>12s}" for t in tags) + "   (accepted share)")
    for g in sorted(groups):
        keys = groups[g]
        exp = runs[tags[0]][keys[0]]["expected"]
        cells = []
        for t in tags:
            acc = sum(runs[t][k]["accepted"] == "True" for k in keys) / len(keys)
            cells.append(f"{acc:12.1%}")
        print(f"{g:34s} {len(keys):4d} {exp:>7s} " + " ".join(cells))


if __name__ == "__main__":
    main()
