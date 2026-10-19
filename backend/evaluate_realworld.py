"""Run real photos through the complete app pipeline (leaf check + region
analysis + Healthy/Damaged classifier) and report what the app would answer.

Put photos in backend/realworld_test/<category>/ (create the folders you need):

  leaf_healthy/        close-ups of single healthy calamansi leaves
  leaf_damaged/        close-ups of single damaged calamansi leaves
  plant_healthy/       calamansi branches/plants (fruit may be visible), healthy leaves
  plant_damaged/       calamansi branches/plants with damaged leaves
  plant_unlabeled/     calamansi branches/plants whose leaf health is not known
                       (only checks that they are accepted)
  fruit_only/          calamansi fruit with no clearly visible leaves (should be rejected)
  not_calamansi/       anything else: other plants or citrus, people, objects (should be rejected)

Only photos you have verified yourself belong here; they are never used for
training. Usage:
    python evaluate_realworld.py
"""
from __future__ import annotations

import json
from pathlib import Path

from config import BACKEND_DIR, OUTPUTS_DIR
from predict import InvalidImageError, Predictor

FOLDER = BACKEND_DIR / "realworld_test"
EXPECT = {
    "leaf_healthy": ("accept", "Healthy"), "leaf_damaged": ("accept", "Damaged"),
    "plant_healthy": ("accept", "Healthy"), "plant_damaged": ("accept", "Damaged"),
    "plant_unlabeled": ("accept", None), "fruit_only": ("reject", None), "not_calamansi": ("reject", None),
}
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def main() -> None:
    if not FOLDER.exists():
        raise SystemExit(f"Create {FOLDER} with sub-folders: {', '.join(EXPECT)}")
    predictor = Predictor()
    rows, summary = [], {}
    for cat, (want, want_class) in EXPECT.items():
        files = sorted(p for p in (FOLDER / cat).glob("*") if p.suffix.lower() in EXTS) if (FOLDER / cat).exists() else []
        correct = 0
        for f in files:
            try:
                r = predictor.predict_file(f)
            except InvalidImageError as e:
                rows.append({"category": cat, "file": f.name, "outcome": f"unreadable: {e}", "correct": False})
                continue
            got = "accept" if r.accepted else "reject"
            ok = got == want and (want_class is None or r.predicted_class == want_class)
            correct += ok
            rows.append({"category": cat, "file": f.name, "outcome": got, "class": r.predicted_class,
                         "confidence": round(r.confidence, 4) if r.confidence is not None else None,
                         "analysis": r.analysis, "regions_used": r.regions_used,
                         "regions_checked": r.regions_checked, "gate_reason": r.gate.reason, "correct": bool(ok)})
            print(f"{'OK ' if ok else 'XX '} {cat:16s} {f.name[:48]:48s} -> {got}"
                  + (f" {r.predicted_class} {r.confidence:.1%} ({r.analysis}, {r.regions_used}/{r.regions_checked} regions)"
                     if r.accepted else f" ({r.gate.reason})"))
        if files:
            summary[cat] = {"correct": correct, "n": len(files), "expected": want + (f" as {want_class}" if want_class else "")}
    print("\nSummary:")
    for cat, v in summary.items():
        print(f"  {cat:16s} {v['correct']}/{v['n']} correct (expected: {v['expected']})")
    out = OUTPUTS_DIR / "realworld_evaluation.json"
    out.write_text(json.dumps({"model_version": predictor.version, "summary": summary, "results": rows}, indent=2),
                   encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
