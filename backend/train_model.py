"""Train the Healthy / Damaged calamansi leaf classifier (transfer learning).

Reads the split manifest written by prepare_dataset.py, trains one or more
candidate architectures, and activates the one with the best validation
performance by writing models/model_metadata.json (which the API loads).

Training recipe (per architecture):
  1. ImageNet-pretrained backbone frozen, new sigmoid head trained (lr 1e-3).
  2. Top of the backbone unfrozen and fine-tuned at a low learning rate (1e-5).
  * augmentation (flip, rotation, zoom, shift, brightness, contrast) on the
    training split only
  * balanced class weights (the dataset has ~1.5 Damaged per Healthy photo)
  * early stopping on validation loss + checkpointing of the best weights

Usage:
    python train_model.py                       # compare mobilenetv2 and efficientnetb0
    python train_model.py --arch mobilenetv2    # train a single architecture
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone

import numpy as np

from config import (
    CLASS_NAMES,
    DATASET_DIR,
    HISTORY_JSON,
    IMG_SIZE,
    METADATA_PATH,
    MODELS_DIR,
    OUTPUTS_DIR,
    SEED,
    SPLITS_CSV,
)
from predict import load_image

ARCHS = ("mobilenetv2", "efficientnetb0")


def load_split(split: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load every image of one split into memory (the dataset is small)."""
    if not SPLITS_CSV.exists():
        raise SystemExit("outputs/splits.csv not found. Run `python prepare_dataset.py` first.")
    with open(SPLITS_CSV, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == split]
    if not rows:
        raise SystemExit(f"No images in split '{split}'. Re-run prepare_dataset.py.")
    x = np.stack([load_image(DATASET_DIR / r["filepath"]) for r in rows])
    y = np.array([CLASS_NAMES.index(r["label"]) for r in rows], dtype=np.float32)
    return x, y, [r["filepath"] for r in rows]


def background_variants(x: np.ndarray, y: np.ndarray, n_comp: int, n_clusters: int, seed: int,
                        split: str) -> tuple[np.ndarray, np.ndarray]:
    """Re-use each leaf on new backgrounds and in branch-like clusters, keeping its label.

    Without this the classifier only ever sees the blue photo sheet and judges
    leaves on other backgrounds unreliably (e.g. healthy foliage -> "Damaged").
    Backgrounds come from the public negative datasets of the same split when
    downloaded (download_ood_data.py), otherwise synthetic surfaces are used.
    """
    import random

    from composites import composite, leaf_cluster

    bg_pool: list = []
    try:
        from train_gate import negative_sources, split_of
        negs = negative_sources(random.Random(SEED))
        bg_pool = [p for c in ("flowers", "everyday_objects", "caltech_objects", "citrus_fruits", "other_plant_leaves")
                   if c in negs for p, g in negs[c] if split_of(f"{c}/{g}") == split]
    except Exception:
        pass
    r = random.Random(seed)
    xs, ys = [], []
    for arr, label in zip(x, y):
        for _ in range(n_comp):
            img = composite(arr, r, bg_pool)
            if img is not None:
                xs.append(np.asarray(img)); ys.append(label)
    for cls in (0.0, 1.0):
        idx = np.nonzero(y == cls)[0]
        made = 0
        while made < n_clusters // 2:
            img = leaf_cluster([x[i] for i in r.sample(list(idx), r.randint(3, 12))], r, bg_pool)
            if img is not None:
                xs.append(np.asarray(img)); ys.append(cls); made += 1
    return np.stack(xs), np.array(ys, dtype=np.float32)


def build_model(arch: str):
    import tensorflow as tf
    from tensorflow.keras import layers

    inputs = layers.Input((IMG_SIZE, IMG_SIZE, 3), name="image_0_255")
    if arch == "mobilenetv2":
        x = layers.Rescaling(1 / 127.5, offset=-1, name="mobilenetv2_preprocess")(inputs)
        base = tf.keras.applications.MobileNetV2(include_top=False, weights="imagenet",
                                                 input_shape=(IMG_SIZE, IMG_SIZE, 3), pooling="avg")
    elif arch == "efficientnetb0":
        x = inputs  # EfficientNet includes its own rescaling/normalisation layers
        base = tf.keras.applications.EfficientNetB0(include_top=False, weights="imagenet",
                                                    input_shape=(IMG_SIZE, IMG_SIZE, 3), pooling="avg")
    else:
        raise ValueError(arch)
    base.trainable = False
    x = base(x, training=False)  # keep BatchNorm in inference mode, also while fine-tuning
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(1, activation="sigmoid", name="p_healthy")(x)
    return tf.keras.Model(inputs, outputs, name=f"calamansi_{arch}"), base


def augmenter():
    import tensorflow as tf
    from tensorflow.keras import layers

    return tf.keras.Sequential([
        layers.RandomFlip("horizontal_and_vertical"),
        layers.RandomRotation(0.25, fill_mode="reflect"),
        layers.RandomZoom((-0.15, 0.25), fill_mode="reflect"),
        layers.RandomTranslation(0.1, 0.1, fill_mode="reflect"),
        layers.RandomBrightness(0.15, value_range=(0, 255)),
        layers.RandomContrast(0.15),
    ], name="train_augmentation")


def make_ds(x, y, batch: int, training: bool):
    import tensorflow as tf

    # Kept as uint8 (4x less memory than float32) and cast per batch; same values.
    ds = tf.data.Dataset.from_tensor_slices((x.astype(np.uint8), y))
    if training:
        aug = augmenter()
        ds = ds.shuffle(len(x), seed=SEED, reshuffle_each_iteration=True).batch(batch)
        ds = ds.map(lambda a, b: (tf.clip_by_value(aug(tf.cast(a, tf.float32), training=True), 0, 255), b),
                    num_parallel_calls=tf.data.AUTOTUNE)
    else:
        ds = ds.batch(batch).map(lambda a, b: (tf.cast(a, tf.float32), b))
    return ds.prefetch(tf.data.AUTOTUNE)


def train_one(arch: str, data: dict, args) -> dict:
    import tensorflow as tf

    tf.keras.utils.set_random_seed(SEED)
    (xtr, ytr), (xva, yva) = data["train"], data["val"]
    counts = np.bincount(ytr.astype(int), minlength=2)
    class_weight = {i: float(len(ytr) / (2 * c)) for i, c in enumerate(counts)}
    print(f"\n=== {arch} === train {dict(zip(CLASS_NAMES, counts.tolist()))}, class weights {class_weight}")

    model, base = build_model(arch)
    ckpt = MODELS_DIR / f"calamansi_{arch}.keras"
    metrics = ["accuracy", tf.keras.metrics.AUC(name="auc")]
    callbacks = lambda patience: [  # noqa: E731
        tf.keras.callbacks.EarlyStopping("val_loss", patience=patience, restore_best_weights=True),
        tf.keras.callbacks.ModelCheckpoint(ckpt, monitor="val_loss", save_best_only=True),
        tf.keras.callbacks.ReduceLROnPlateau("val_loss", factor=0.3, patience=2, min_lr=1e-7),
    ]
    train_ds, val_ds = make_ds(xtr, ytr, args.batch, True), make_ds(xva, yva, args.batch, False)

    t0 = time.time()
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy", metrics=metrics)
    h1 = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs_head,
                   class_weight=class_weight, callbacks=callbacks(4), verbose=2)
    head_val_loss = model.evaluate(val_ds, verbose=0)[0]
    head_weights = model.get_weights()

    # Fine-tune the top of the backbone; BatchNorm layers stay frozen.
    base.trainable = True
    cut = len(base.layers) - args.finetune_layers
    for i, layer in enumerate(base.layers):
        layer.trainable = i >= cut and not isinstance(layer, tf.keras.layers.BatchNormalization)
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-5), loss="binary_crossentropy", metrics=metrics)
    h2 = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs_finetune,
                   class_weight=class_weight, callbacks=callbacks(5), verbose=2)
    minutes = (time.time() - t0) / 60
    if model.evaluate(val_ds, verbose=0)[0] > head_val_loss:
        print("Fine-tuning did not improve validation loss; keeping the frozen-backbone weights.")
        model.set_weights(head_weights)

    model.save(ckpt)  # best weights were restored by EarlyStopping
    val_loss, val_acc, val_auc = model.evaluate(val_ds, verbose=0)
    history = {k: [float(v) for v in h1.history.get(k, []) + h2.history.get(k, [])]
               for k in ("loss", "accuracy", "auc", "val_loss", "val_accuracy", "val_auc")}
    history["finetune_start_epoch"] = len(h1.history["loss"])
    print(f"{arch}: val_loss {val_loss:.4f} val_acc {val_acc:.4f} val_auc {val_auc:.4f} ({minutes:.1f} min)")
    return {"arch": arch, "model_file": ckpt.name, "val_loss": val_loss, "val_accuracy": val_acc,
            "val_auc": val_auc, "train_minutes": round(minutes, 1), "epochs": len(history["loss"]),
            "params": int(model.count_params()), "history": history, "class_weight": class_weight}


def plot_history(results: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(results), 2, figsize=(11, 3.6 * len(results)), squeeze=False)
    for row, r in zip(axes, results):
        h = r["history"]
        for ax, key in zip(row, ("loss", "accuracy")):
            ax.plot(h[key], label=f"train {key}")
            ax.plot(h[f"val_{key}"], label=f"val {key}")
            ax.axvline(h["finetune_start_epoch"] - 0.5, color="grey", ls="--", lw=1, label="fine-tune start")
            ax.set_title(f"{r['arch']} - {key}")
            ax.set_xlabel("epoch")
            ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUTS_DIR / "training_curves.png", dpi=110)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", choices=ARCHS + ("all",), default="all")
    ap.add_argument("--epochs-head", type=int, default=15)
    ap.add_argument("--epochs-finetune", type=int, default=15)
    ap.add_argument("--finetune-layers", type=int, default=40, help="backbone layers to unfreeze")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--no-background-aug", action="store_true",
                    help="train on the original photos only (no leaves on new backgrounds / in clusters)")
    args = ap.parse_args()

    archs = ARCHS if args.arch == "all" else (args.arch,)
    print("Loading images...")
    data = {s: load_split(s)[:2] for s in ("train", "val")}
    photo_counts = {c: int((data["train"][1] == i).sum()) for i, c in enumerate(CLASS_NAMES)}
    if not args.no_background_aug:
        print("Building leaves-on-new-backgrounds and branch-like cluster variants...")
        for split, n_comp, n_clusters, seed in (("train", 2, 600, SEED), ("val", 1, 100, SEED + 1)):
            vx, vy = background_variants(*data[split], n_comp, n_clusters, seed, split)
            data[split] = (np.concatenate([data[split][0], vx]), np.concatenate([data[split][1], vy]))
            print(f"  {split}: +{len(vx)} variants -> {len(data[split][0])} images")
    results = [train_one(a, data, args) for a in archs]

    # Activate the best candidate: lowest validation loss, accuracy as tie-break.
    best = min(results, key=lambda r: (round(r["val_loss"], 3), -r["val_accuracy"]))
    trained_at = datetime.now(timezone.utc)
    metadata = {
        "model_file": best["model_file"],
        "architecture": best["arch"],
        "model_version": f"{best['arch']}-{trained_at:%Y%m%d-%H%M}",
        "trained_at": trained_at.isoformat(),
        "class_names": CLASS_NAMES,
        "output": "sigmoid = P(Healthy); confidence = probability of the predicted class",
        "threshold": 0.5,
        "img_size": IMG_SIZE,
        "preprocessing": "EXIF-rotate, RGB, bilinear resize to 224x224, raw 0-255 input (normalisation inside model)",
        "train_counts": photo_counts,
        "background_augmentation": not args.no_background_aug,
        "validation": {"loss": round(best["val_loss"], 4), "accuracy": round(best["val_accuracy"], 4),
                       "auc": round(best["val_auc"], 4)},
        "candidates": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != "history"}
                       for r in results],
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    HISTORY_JSON.write_text(json.dumps({r["arch"]: r["history"] for r in results}, indent=2), encoding="utf-8")
    plot_history(results)
    print(f"\nSelected {best['arch']} (val_loss {best['val_loss']:.4f}, val_acc {best['val_accuracy']:.4f}).")
    print(f"Wrote {METADATA_PATH}\nNext: python evaluate_model.py")


if __name__ == "__main__":
    main()
