"""Evaluate the active model on the independent test split.

Outputs (in backend/outputs/):
  evaluation_metrics.json   accuracy, precision/recall/F1 per class, ROC AUC,
                            confusion matrix, overfitting check, subgroup results
  confusion_matrix.png
  classification_report.txt
  misclassified_test.csv    test images the model got wrong (review these:
                            some may be mislabelled, others are model weaknesses)
  label_review_train.csv    training images the model contradicts with >= 80%
                            confidence - the most likely labelling mistakes

Usage:
    python evaluate_model.py
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

import numpy as np
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

from config import CLASS_NAMES, EVALUATION_JSON, OUTPUTS_DIR, SEED
from predict import Predictor
from prepare_dataset import background_kind, border_rgb
from train_model import load_split


def predict_probs(predictor: Predictor, x: np.ndarray) -> np.ndarray:
    """P(Healthy) for each image."""
    return predictor.model.predict(x.astype(np.float32), batch_size=32, verbose=0).ravel()


def summarize(y: np.ndarray, p_healthy: np.ndarray, threshold: float) -> dict:
    pred = (p_healthy >= threshold).astype(int)
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
    out = {
        "n": int(len(y)),
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "per_class": {c: {"precision": round(float(prec[i]), 4), "recall": round(float(rec[i]), 4),
                          "f1": round(float(f1[i]), 4), "support": int(sup[i])} for i, c in enumerate(CLASS_NAMES)},
        "macro_f1": round(float(f1.mean()), 4),
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }
    if len(set(y.tolist())) == 2:
        out["roc_auc"] = round(float(roc_auc_score(y, p_healthy)), 4)
    return out


def plot_confusion(cm: list[list[int]], title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cm = np.array(cm)
    fig, ax = plt.subplots(figsize=(4.6, 4))
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks([0, 1], CLASS_NAMES)
    ax.set_yticks([0, 1], CLASS_NAMES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=14,
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.tight_layout()
    fig.savefig(OUTPUTS_DIR / "confusion_matrix.png", dpi=120)


def main() -> None:
    predictor = Predictor(require_gate=False)  # evaluates the Healthy/Damaged classifier alone
    t = predictor.threshold
    print(f"Model: {predictor.version}  (threshold {t})")

    results = {}
    for split in ("train", "val", "test"):
        x, y, files = load_split(split)
        p = predict_probs(predictor, x)
        results[split] = summarize(y, p, t)
        if split == "test":
            x_test, y_test, files_test, p_test = x, y, files, p
        if split == "train":
            suspects = [{"filepath": f, "label": CLASS_NAMES[int(yt)], "model_says": CLASS_NAMES[int(pt >= t)],
                         "p_healthy": round(float(pt), 4)}
                        for f, yt, pt in zip(files, y, p) if abs(float(pt) - yt) >= 0.8]

    test = results["test"]
    report_txt = classification_report(y_test, (p_test >= t).astype(int), labels=[0, 1],
                                       target_names=CLASS_NAMES, digits=4, zero_division=0)
    (OUTPUTS_DIR / "classification_report.txt").write_text(
        f"Model {predictor.version} - independent test split ({test['n']} images)\n\n{report_txt}", encoding="utf-8")
    plot_confusion(test["confusion_matrix"], f"Test set ({test['n']} images)")

    # Background subgroups: white-backdrop photos exist only in the Damaged class, so
    # accuracy on blue-backdrop photos alone shows whether the model relies on the leaf.
    bg = np.array([background_kind(border_rgb(Image.fromarray(a))) for a in x_test])
    # Robustness: the same held-out test leaves, cut out and shown on new backgrounds
    # and in branch-like clusters (fixed seed, so every model is scored on identical images).
    from train_model import background_variants

    vx, vy = background_variants(x_test, y_test, 2, 200, SEED + 2, "test")
    n_single = len(vx) - 200
    pv = predict_probs(predictor, vx)
    new_bg = {"single_leaf_new_background": summarize(vy[:n_single], pv[:n_single], t),
              "branch_like_clusters": summarize(vy[n_single:], pv[n_single:], t)}

    subgroups = {kind: summarize(y_test[bg == kind], p_test[bg == kind], t)
                 for kind in sorted(set(bg)) if (bg == kind).sum() >= 5}

    wrong = []
    for f, yt, pt in zip(files_test, y_test, p_test):
        pred = int(pt >= t)
        if pred != yt:
            wrong.append({"filepath": f, "actual": CLASS_NAMES[int(yt)], "predicted": CLASS_NAMES[pred],
                          "p_healthy": round(float(pt), 4)})
    with open(OUTPUTS_DIR / "misclassified_test.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["filepath", "actual", "predicted", "p_healthy"])
        w.writeheader()
        w.writerows(wrong)

    with open(OUTPUTS_DIR / "label_review_train.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["filepath", "label", "model_says", "p_healthy"])
        w.writeheader()
        w.writerows(suspects)

    gap = results["train"]["accuracy"] - test["accuracy"]
    metrics = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": predictor.version,
        "architecture": predictor.metadata.get("architecture"),
        "trained_at": predictor.metadata.get("trained_at"),
        "threshold": t,
        "test": test,
        "validation": results["val"],
        "train_no_augmentation": results["train"],
        "overfitting_check": {
            "train_minus_test_accuracy": round(gap, 4),
            "assessment": "large gap - likely overfitting" if gap > 0.08 else
                          "moderate gap" if gap > 0.03 else "small gap - no strong sign of overfitting",
        },
        "test_by_background": subgroups,
        "test_leaves_on_new_backgrounds": new_bg,
        "misclassified_test_count": len(wrong),
        "train_label_review_count": len(suspects),
        "notes": [
            "Metrics are from the held-out test split, which was never used for training or model selection.",
            "All white-background photos are Damaged; see test_by_background for blue-background-only accuracy.",
            "The model only knows two classes. Non-leaf images will still be labelled Healthy or Damaged.",
        ],
    }
    EVALUATION_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"\nIndependent test set ({test['n']} images)\n{report_txt}")
    print(f"ROC AUC: {test.get('roc_auc')}")
    print(f"Confusion matrix [rows=actual {CLASS_NAMES}, cols=predicted]: {test['confusion_matrix']}")
    print(f"Accuracy train(no aug) {results['train']['accuracy']} | val {results['val']['accuracy']} | "
          f"test {test['accuracy']} -> {metrics['overfitting_check']['assessment']}")
    for kind, s in new_bg.items():
        print(f"Test leaves, {kind.replace('_', ' ')}: n={s['n']} accuracy={s['accuracy']} "
              f"(Healthy recall {s['per_class']['Healthy']['recall']}, Damaged recall {s['per_class']['Damaged']['recall']})")
    for kind, s in subgroups.items():
        print(f"Test subgroup '{kind}' background: n={s['n']} accuracy={s['accuracy']}")
    print(f"Misclassified test images: {len(wrong)} (see outputs/misclassified_test.csv)")
    print(f"Training images to re-check (model disagrees with >=80% confidence): {len(suspects)} "
          f"(see outputs/label_review_train.csv)")
    print(f"Wrote {EVALUATION_JSON}")


if __name__ == "__main__":
    main()
