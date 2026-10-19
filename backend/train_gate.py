"""Train the calamansi-leaf gate: decides whether an image shows a calamansi leaf
at all, before the Healthy/Damaged classifier is allowed to run.

Why it is needed: the Healthy/Damaged model was trained only on calamansi leaves.
Its single sigmoid output must be either Healthy or Damaged, so a face or a
lemon leaf also gets one of those labels, often with high confidence.

How the gate works (an image is accepted only if every check passes):
  Stage 1 (frozen ImageNet MobileNetV2 features):
    a. logistic regression: calamansi photos vs. public datasets of other
       leaves (incl. other citrus), citrus fruit, flowers, objects and people
       (see download_ood_data.py);
    b. novelty check: distance to the nearest calamansi training example.
       Rejects unusual inputs that none of the negative datasets cover.
  Stage 2: a MobileNetV2 fine-tuned end to end on the same task. It learns
    finer leaf cues, which matters most for other citrus leaves.

Positives are augmented, and the leaf is also cut out of its plain blue/white
backdrop and pasted onto other backgrounds, so the gate learns the leaf rather
than the photo sheet.

Thresholds are chosen on the validation split only (keep >= 98% of calamansi
validation images). Reports (outputs/gate_evaluation.json):
  * acceptance of calamansi test photos (plain and on new backgrounds)
  * rejection rate per negative category on held-out test images
  * leave-one-dataset-out for stage 1, and `--unseen a,b` to retrain the whole
    gate without some categories and test it on them

Usage:
    python download_ood_data.py
    python train_gate.py
    python train_gate.py --unseen people,flowers   # optional generalisation experiment
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from config import CLASS_NAMES, DATASET_DIR, IMG_SIZE, MODELS_DIR, OUTPUTS_DIR, SEED, SPLITS_CSV
from download_ood_data import OOD_DIR
from composites import augment, composite, leaf_cluster, leaf_mask, random_background
from predict import GATE_EXTRACTOR_PATH, GATE_PATH, InvalidImageError, load_image

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
# Bump the version whenever predict.load_image changes, so stale features are never reused
# (v2: non-square photos are padded to a square instead of squashed).
PREPROCESS_VERSION = "v2-pad"
CACHE = OUTPUTS_DIR / f"gate_embeddings_cache_{PREPROCESS_VERSION}.npz"
POS_TARGET_ACCEPT = 0.99      # keep >= 99% of validation calamansi photos
NOVELTY_PERCENTILE = 99.5     # novelty threshold = this percentile of validation calamansi distances


# --------------------------------------------------------------------------- data
def split_of(key: str) -> str:
    """Deterministic 70/15/15 split from a stable hash of the file path / group.

    Real iNaturalist photos ("inat_..." keys, one group per observation) are split 50/15/35,
    so a larger share of these scarce real-world photos stays held out for testing."""
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    if key.startswith("inat_"):
        return "train" if h < 50 else "val" if h < 65 else "test"
    return "train" if h < 70 else "val" if h < 85 else "test"


INAT_DIR = OOD_DIR / "inat"
INAT_OTHER_CITRUS = ("lemon", "key_lime", "persian_lime", "makrut_lime", "orange")


def inat_calamansi() -> list[tuple[Path, str]]:
    """Real calamansi photos from iNaturalist whose leaves are clearly visible (manual review,
    ood_data/inat/calamansi_labels.csv) -> [(path, split)]. Photos without clear leaves are
    not used: fruit or flowers alone must not teach the check that they are calamansi leaves."""
    lab = INAT_DIR / "calamansi_labels.csv"
    if not lab.exists():
        return []
    rows = list(csv.DictReader(open(lab, encoding="utf-8")))
    return [(INAT_DIR / r["file"], split_of(f"inat_calamansi/{Path(r['file']).stem}"))
            for r in rows if r["leaves"] == "yes" and (INAT_DIR / r["file"]).exists()]


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXT and p.is_file())


def near_duplicate_groups(paths: list[Path], threshold: float = 0.95) -> dict[Path, str]:
    """Group burst shots / re-uploads of the same leaf (also across datasets), so that a
    group never ends up in two splits. Similarity: correlation of 32x32 grayscale
    thumbnails (and of the mirrored thumbnail). Returns path -> group id."""
    if not paths:
        return {}
    cache = OUTPUTS_DIR / "near_duplicate_thumbs.npz"
    known = {}
    if cache.exists():
        z = np.load(cache)
        known = dict(zip(z["keys"].tolist(), z["vals"]))
    vecs = []
    for p in paths:
        key = str(p)
        if key not in known:
            try:
                with Image.open(p) as im:
                    known[key] = np.asarray(im.convert("L").resize((32, 32), Image.BILINEAR), np.float32).ravel()
            except Exception:  # noqa: BLE001 - unreadable file: its own group
                known[key] = np.zeros(1024, np.float32)
        vecs.append(known[key])
    np.savez(cache, keys=np.array(list(known), dtype=str), vals=np.stack(list(known.values())))
    x = np.stack(vecs)

    def norm(a):
        a = a - a.mean(1, keepdims=True)
        return a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-6)

    xn, xm = norm(x), norm(x.reshape(-1, 32, 32)[:, :, ::-1].reshape(len(x), -1))
    parent = list(range(len(paths)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for start in range(0, len(paths), 1024):
        block = xn[start:start + 1024]
        sim = np.maximum(block @ xn.T, block @ xm.T)
        for a, b in zip(*np.nonzero(sim >= threshold)):
            i, j = start + int(a), int(b)
            if i < j:
                parent[find(i)] = find(j)
    return {p: f"g{find(i)}:{paths[find(i)].name}" for i, p in enumerate(paths)}


def negative_sources(rng: random.Random) -> dict[str, list[tuple[Path, str]]]:
    """category -> [(path, group)], capped per category to keep the sets balanced.

    The group decides the train/val/test split: one image per group, except that
    all photos of the same person (LFW) share a group so a face never appears in
    two splits.
    """
    out: dict[str, list[tuple[Path, str]]] = {}

    def take(cat: str, items: list[tuple[Path, str]], cap: int):
        rng.shuffle(items)
        if items:
            out[cat] = sorted(items[:cap])

    def files(name: str) -> list[Path]:
        d = OOD_DIR / name / "files"
        return list_images(d) if d.exists() else []

    citrus = files("citrus_leaves")
    take("other_citrus_leaves", [(p, p.name) for p in citrus if "Leaves" in p.parts], 700)
    take("citrus_fruits", [(p, p.name) for p in citrus if "Fruits" in p.parts], 300)
    pv = files("plant_village")
    take("other_citrus_leaves_plantvillage", [(p, p.name) for p in pv if "orange" in p.parent.name.lower()], 500)
    by_class = defaultdict(list)
    for p in pv:
        if "orange" not in p.parent.name.lower():
            by_class[p.parent.name].append(p)
    pv_other = []
    for cls, ps in by_class.items():
        rng.shuffle(ps)
        pv_other += [(p, f"{cls}/{p.name}") for p in ps[:90]]
    take("other_plant_leaves", pv_other, 3000)
    take("flowers", [(p, p.name) for p in files("tf_flowers")], 700)
    take("everyday_objects", [(p, p.name) for p in files("imagenette")], 900)
    cal = defaultdict(list)
    for p in files("caltech101"):
        cal[p.parent.name].append(p)
    cal_items = []
    for cls, ps in cal.items():
        rng.shuffle(ps)
        cal_items += [(p, f"{cls}/{p.name}") for p in ps[:12]]
    take("caltech_objects", cal_items, 1200)
    lfw = defaultdict(list)
    for p in files("lfw"):
        lfw[p.parent.name].append(p)
    take("people", [(ps[0], person) for person, ps in lfw.items()], 800)

    # Species-labelled single leaves of other citrus: the negatives that look most like calamansi.
    # Healthy and diseased leaves are balanced, so the check does not learn "damage = not calamansi".
    lemon = [p for p in files("lemon_bd") if "Raw Image" in p.parts] + files("lemon_jamalpur")
    orange = [p for p in files("orange_hlb") if "visualizations" not in p.parts]  # skip the dataset's charts
    groups = near_duplicate_groups(lemon + orange)
    healthy = lambda p: any(w in part.lower() for part in p.parts[-3:-1] for w in ("healthy", "healty"))  # noqa: E731 (class folder; "Healty" sic)
    lemon_h, lemon_d = [p for p in lemon if healthy(p)], [p for p in lemon if not healthy(p)]
    rng.shuffle(lemon_d)
    take("lemon_leaves", [(p, groups[p]) for p in lemon_h + lemon_d[:max(len(lemon_h), 600)]], 1600)
    orange_h, orange_d = [p for p in orange if healthy(p)], [p for p in orange if not healthy(p)]
    rng.shuffle(orange_h)
    rng.shuffle(orange_d)
    take("orange_leaves_hlb", [(p, groups[p]) for p in orange_h[:500] + orange_d[:500]], 1000)
    # Real photos of other citrus plants (lemon, limes, orange) from iNaturalist, one per observation.
    # The category name starts with "inat_" so these use the 50/15/35 split (see split_of).
    inat = [(p, f"{sp}/{p.stem}") for sp in INAT_OTHER_CITRUS for p in sorted((INAT_DIR / sp).glob("*.jpg"))]
    random.Random(SEED + 99).shuffle(inat)  # own RNG: adding this test-only category changes no other draw
    out["inat_other_citrus"] = sorted(inat[:2000])
    return out


def remove_leaf(arr: np.ndarray, alpha: np.ndarray, seed: int) -> np.ndarray:
    """Paint the leaf out of a sheet photo using the surrounding sheet colours.

    Normalised blur: the sheet outside a slightly widened leaf mask is blurred and
    divided by the blurred mask, so the hole is filled with the local lighting
    gradient instead of a flat, leaf-shaped patch (which would itself be a shape cue).
    """
    hole = Image.fromarray(((alpha > 0.05) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))
    keep = 1.0 - np.asarray(hole, dtype=np.float32)[..., None] / 255
    def blur(x: np.ndarray, radius: float) -> np.ndarray:
        chans = [np.asarray(Image.fromarray(x[..., i]).filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
                 for i in range(x.shape[-1])]
        return np.stack(chans, -1)
    src = arr.astype(np.float32) * keep
    num = blur(np.clip(src, 0, 255).astype(np.uint8), 30) / 255 * 255
    den = blur((keep * 255).astype(np.uint8), 30) / 255
    filled = num / np.maximum(den, 1e-3)
    grain = np.random.default_rng(seed).normal(0, 3, arr.shape)
    out = arr.astype(np.float32) * keep + (filled + grain) * (1 - keep)
    return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- features
class Extractor:
    def __init__(self):
        import tensorflow as tf
        from tensorflow.keras import layers

        if GATE_EXTRACTOR_PATH.exists():
            self.model = tf.keras.models.load_model(GATE_EXTRACTOR_PATH)
        else:
            inp = layers.Input((IMG_SIZE, IMG_SIZE, 3))
            x = layers.Rescaling(1 / 127.5, offset=-1)(inp)
            base = tf.keras.applications.MobileNetV2(include_top=False, weights="imagenet",
                                                     input_shape=(IMG_SIZE, IMG_SIZE, 3), pooling="avg")
            self.model = tf.keras.Model(inp, base(x, training=False), name="leaf_gate_extractor")
            self.model.save(GATE_EXTRACTOR_PATH)

    def __call__(self, arrs: list[np.ndarray]) -> np.ndarray:
        out = self.model.predict(np.stack(arrs).astype(np.float32), batch_size=64, verbose=0)
        return out / np.linalg.norm(out, axis=1, keepdims=True)


def embed_files(ext: Extractor, paths: list[Path], cache: dict) -> np.ndarray:
    todo = [p for p in paths if str(p) not in cache]
    for i in range(0, len(todo), 256):
        chunk, arrs = todo[i:i + 256], []
        ok = []
        for p in chunk:
            try:
                arrs.append(load_image(p))
                ok.append(p)
            except InvalidImageError:
                cache[str(p)] = None
        if arrs:
            for p, e in zip(ok, ext(arrs)):
                cache[str(p)] = e
        print(f"  embedded {min(i + 256, len(todo))}/{len(todo)}", end="\r")
    return np.stack([cache[str(p)] for p in paths if cache.get(str(p)) is not None])


# --------------------------------------------------------------------------- model
class Gate:
    def __init__(self, n_components: int = 128, C: float = 0.5):
        self.n_components, self.C = n_components, C

    def fit(self, pos: np.ndarray, neg: np.ndarray):
        from sklearn.decomposition import PCA
        from sklearn.linear_model import LogisticRegression

        x = np.concatenate([pos, neg])
        y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
        self.clf = LogisticRegression(C=self.C, class_weight="balanced", max_iter=5000).fit(x, y)
        self.pca = PCA(self.n_components, random_state=SEED).fit(pos)
        self.bank = self.pca.transform(pos).astype(np.float32)
        return self

    def prob(self, x: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(x)[:, 1]

    def novelty(self, x: np.ndarray) -> np.ndarray:
        """Distance to the nearest calamansi training example (PCA space)."""
        z = self.pca.transform(x).astype(np.float32)
        out = np.empty(len(z), dtype=np.float32)
        for i in range(0, len(z), 512):
            d = ((z[i:i + 512, None, :] - self.bank[None]) ** 2).sum(-1)
            out[i:i + 512] = np.sqrt(d.min(1))
        return out

    def calibrate(self, val_pos: np.ndarray):
        self.t_prob = float(np.quantile(self.prob(val_pos), 1 - POS_TARGET_ACCEPT))
        self.t_dist = float(np.percentile(self.novelty(val_pos), NOVELTY_PERCENTILE))
        return self

    def accept(self, x: np.ndarray) -> np.ndarray:
        return (self.prob(x) >= self.t_prob) & (self.novelty(x) <= self.t_dist)

    def save(self, path: Path):
        np.savez_compressed(
            path, coef=self.clf.coef_[0].astype(np.float32), intercept=np.float32(self.clf.intercept_[0]),
            pca_mean=self.pca.mean_.astype(np.float32), pca_components=self.pca.components_.astype(np.float32),
            bank=self.bank, t_prob=np.float32(self.t_prob), t_dist=np.float32(self.t_dist))


# --------------------------------------------------------------------------- stage 2: fine-tuned CNN
def train_cnn(pos_train: np.ndarray, pos_train_weight: np.ndarray, neg_train: np.ndarray, neg_train_weight: np.ndarray,
              pos_val: np.ndarray, neg_val: np.ndarray, out_path: Path, epochs_head: int, epochs_ft: int):
    """Binary MobileNetV2 (calamansi leaf vs. anything else), fine-tuned end to end.

    A linear model on frozen ImageNet features separates calamansi from other
    citrus leaves poorly; fine-tuning lets the network learn finer leaf cues.
    """
    import tensorflow as tf
    from tensorflow.keras import layers

    from train_model import augmenter

    tf.keras.utils.set_random_seed(SEED)
    x = np.concatenate([pos_train, neg_train])
    y = np.r_[np.ones(len(pos_train)), np.zeros(len(neg_train))].astype(np.float32)
    # Balance the two classes; within each class, hard examples count more: other citrus
    # among the negatives, visibly damaged calamansi leaves among the positives.
    w = np.r_[pos_train_weight * len(x) / (2 * pos_train_weight.sum()),
              neg_train_weight * len(x) / (2 * neg_train_weight.sum())].astype(np.float32)
    order = np.random.default_rng(SEED).permutation(len(x))

    def gen():  # yields from the uint8 arrays without copying them into a second tensor
        for i in np.random.default_rng().permutation(order):
            yield x[i], y[i], w[i]

    sig = (tf.TensorSpec((IMG_SIZE, IMG_SIZE, 3), tf.uint8), tf.TensorSpec((), tf.float32), tf.TensorSpec((), tf.float32))
    aug = augmenter()
    train_ds = (tf.data.Dataset.from_generator(gen, output_signature=sig).batch(32)
                .map(lambda a, b, c: (tf.clip_by_value(aug(tf.cast(a, tf.float32), training=True), 0, 255), b, c))
                .prefetch(2))
    xv = np.concatenate([pos_val, neg_val])
    yv = np.r_[np.ones(len(pos_val)), np.zeros(len(neg_val))].astype(np.float32)
    val_ds = tf.data.Dataset.from_generator(lambda: ((xv[i], yv[i]) for i in range(len(xv))),
                                            output_signature=sig[:2]).batch(64).map(lambda a, b: (tf.cast(a, tf.float32), b))

    inp = layers.Input((IMG_SIZE, IMG_SIZE, 3))
    h = layers.Rescaling(1 / 127.5, offset=-1)(inp)
    base = tf.keras.applications.MobileNetV2(include_top=False, weights="imagenet",
                                             input_shape=(IMG_SIZE, IMG_SIZE, 3), pooling="avg")
    base.trainable = False
    h = layers.Dropout(0.3)(base(h, training=False))
    model = tf.keras.Model(inp, layers.Dense(1, activation="sigmoid", name="p_calamansi_leaf")(h), name="leaf_gate_cnn")
    cb = lambda pat: [tf.keras.callbacks.EarlyStopping("val_loss", patience=pat, restore_best_weights=True),  # noqa: E731
                      tf.keras.callbacks.ReduceLROnPlateau("val_loss", factor=0.3, patience=2)]
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy", metrics=["accuracy"])
    model.fit(train_ds, validation_data=val_ds, epochs=epochs_head, callbacks=cb(2), verbose=2)
    base.trainable = True
    for i, layer in enumerate(base.layers):
        layer.trainable = i >= len(base.layers) - 40 and not isinstance(layer, tf.keras.layers.BatchNormalization)
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-5), loss="binary_crossentropy", metrics=["accuracy"])
    model.fit(train_ds, validation_data=val_ds, epochs=epochs_ft, callbacks=cb(3), verbose=2)
    model.save(out_path)
    return model


def cnn_scores(model, imgs: np.ndarray) -> np.ndarray:
    return model.predict(imgs.astype(np.float32), batch_size=64, verbose=0).ravel() if len(imgs) else np.zeros(0)


def load_all(paths: list[Path]) -> np.ndarray:
    arrs = []
    for p in paths:
        try:
            arrs.append(load_image(p))
        except InvalidImageError:
            pass
    return np.stack(arrs) if arrs else np.zeros((0, IMG_SIZE, IMG_SIZE, 3), np.uint8)


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs-head", type=int, default=4)
    ap.add_argument("--epochs-finetune", type=int, default=8)
    ap.add_argument("--unseen", default="",
                    help="comma-separated negative categories to leave out of ALL training, to measure how the "
                         "complete gate handles kinds of images it has never seen (an experiment, saved separately)")
    args = ap.parse_args()
    unseen = [c for c in args.unseen.split(",") if c]

    rng = random.Random(SEED)
    if not SPLITS_CSV.exists():
        raise SystemExit("outputs/splits.csv not found. Run `python prepare_dataset.py` first.")
    # Real iNaturalist plant photos are used only to TEST the check (evaluate_species.py, evaluate_gate.py):
    # training on the few verified real calamansi photos lowered rejection of other citrus and objects
    # (experiment: experiments/species_round2_patch.py, RESULTS.md section 8).
    negs = {c: v for c, v in negative_sources(rng).items() if not c.startswith("inat_")}
    if not negs:
        raise SystemExit("No negative datasets found. Run `python download_ood_data.py` first.")
    print("Negative categories:", {k: len(v) for k, v in negs.items()}, flush=True)

    with open(SPLITS_CSV, encoding="utf-8") as f:
        pos_rows = list(csv.DictReader(f))
    pos = {s: [DATASET_DIR / r["filepath"] for r in pos_rows if r["split"] == s] for s in ("train", "val", "test")}
    pos_labels = {s: [r["label"] for r in pos_rows if r["split"] == s] for s in ("train", "val", "test")}

    neg_split = {c: {s: [p for p, g in items if split_of(f"{c}/{g}") == s] for s in ("train", "val", "test")}
                 for c, items in negs.items()}
    trained_on = [c for c in neg_split if c not in unseen]
    # Backgrounds for composites: non-leaf training negatives only (no leakage into val/test).
    bg_pool = [p for c in ("flowers", "everyday_objects", "caltech_objects") if c in trained_on
               for p in neg_split[c]["train"]]
    # Branch-like clusters may also stand in front of foliage or citrus fruit: calamansi
    # leaves next to fruit are still calamansi leaves (fruit alone stays a negative).
    cluster_bg = bg_pool + [p for c in ("citrus_fruits", "other_plant_leaves") if c in trained_on
                            for p in neg_split[c]["train"]]

    ext = Extractor()
    cache: dict = {}
    if CACHE.exists():
        data = np.load(CACHE)
        cache = dict(zip(data["keys"].tolist(), data["vals"]))

    print("Embedding calamansi photos...", flush=True)
    P = {s: embed_files(ext, pos[s], cache) for s in pos}
    print("\nEmbedding negatives...", flush=True)
    N = {c: {s: embed_files(ext, ps, cache) if ps else np.zeros((0, 1280), np.float32) for s, ps in d.items()}
         for c, d in neg_split.items()}
    ok = {k: v for k, v in cache.items() if v is not None}
    np.savez(CACHE, keys=np.array(list(ok), dtype=str), vals=np.stack(list(ok.values())).astype(np.float32))

    print("\nBuilding augmented / re-backgrounded calamansi examples...", flush=True)

    def variants(paths: list[Path], n_aug: int, n_comp: int, seed: int) -> np.ndarray:
        r = random.Random(seed)
        out = []
        for p in paths:
            arr = load_image(p)
            out += [np.asarray(augment(Image.fromarray(arr), r)) for _ in range(n_aug)]
            for _ in range(n_comp):
                c = composite(arr, r, bg_pool)
                if c is not None:
                    out.append(np.asarray(augment(c, r)))
        return np.stack(out)

    def feats(imgs: np.ndarray) -> np.ndarray:
        return np.concatenate([ext(list(imgs[i:i + 256])) for i in range(0, len(imgs), 256)])

    def clusters(paths: list[Path], labels: list[str], n: int, seed: int) -> np.ndarray:
        """n branch-like scenes, each from 3-12 calamansi leaves of one label in this split."""
        r = random.Random(seed)
        by_label = {lab: [p for p, l in zip(paths, labels) if l == lab] for lab in set(labels)}
        out = []
        while len(out) < n:
            group = r.sample(by_label[r.choice(sorted(by_label))], r.randint(3, 12))
            img = leaf_cluster([load_image(p) for p in group], r, cluster_bg)
            if img is not None:
                out.append(np.asarray(img))
        return np.stack(out)

    train_var_img = np.concatenate([variants(pos["train"], 2, 4, SEED),
                                    clusters(pos["train"], pos_labels["train"], 1500, SEED + 10)])
    val_cluster_img = clusters(pos["val"], pos_labels["val"], 200, SEED + 11)
    test_cluster_img = clusters(pos["test"], pos_labels["test"], 200, SEED + 12)
    val_var_img = np.concatenate([variants(pos["val"], 0, 2, SEED + 1), val_cluster_img])   # composites + clusters
    test_var_img = variants(pos["test"], 0, 2, SEED + 2)
    train_var, val_var, test_var = feats(train_var_img), feats(val_var_img), feats(test_var_img)

    def empty_backgrounds(paths: list[Path], n_synth: int, seed: int) -> np.ndarray:
        """Backgrounds WITHOUT a leaf, as negatives.

        Positives show calamansi leaves on the blue photo sheet and on synthetic
        surfaces; without these negatives the gate learns "blue sheet / synthetic
        surface = calamansi" and accepts blank or noise images.
        """
        r = random.Random(seed)
        out = []
        for path in paths:  # the real photo sheet with the leaf painted out
            arr = load_image(path)
            m = leaf_mask(arr)
            if m is None:
                continue
            img = Image.fromarray(remove_leaf(arr, m, r.randint(0, 1 << 30))).filter(ImageFilter.GaussianBlur(r.uniform(0, 1.0)))
            out.append(np.asarray(augment(img, r)))
        for _ in range(n_synth):  # the synthetic surfaces used behind composites, with no leaf
            out.append(np.asarray(augment(random_background(r, []), r)))
        return np.stack(out)

    print("Building empty-background negatives...", flush=True)
    empty = {"train": empty_backgrounds(pos["train"], 700, SEED + 20),
             "val": empty_backgrounds(pos["val"][:80], 150, SEED + 21),
             "test": empty_backgrounds(pos["test"][:80], 150, SEED + 22)}
    N["empty_backgrounds"] = {split: feats(imgs) for split, imgs in empty.items()}
    train_pos = np.concatenate([P["train"], train_var])
    val_pos_all = np.concatenate([P["val"], val_var])
    print(f"Train positives: {len(train_pos)} ({len(P['train'])} photos + {len(train_var)} variants)", flush=True)

    def neg_of(split: str, exclude: list[str] = ()) -> np.ndarray:
        return np.concatenate([N[c][split] for c in N if c not in exclude and len(N[c][split])])

    # ---- stage 1: linear classifier + novelty check on frozen features
    best = None
    for C in (0.1, 0.3, 1.0, 3.0):
        g = Gate(C=C).fit(train_pos, neg_of("train", unseen)).calibrate(val_pos_all)
        rej = 1 - g.accept(neg_of("val", unseen)).mean()
        print(f"  C={C}: validation negatives rejected {rej:.4f}", flush=True)
        if best is None or rej > best[0]:
            best = (rej, C)
    gate = Gate(C=best[1]).fit(train_pos, neg_of("train", unseen))
    # Stage 1 is deliberately loose (keeps 99.5% of calamansi); stage 2 does the fine separation.
    gate.t_prob = float(np.quantile(gate.prob(val_pos_all), 0.005))
    gate.t_dist = float(np.percentile(gate.novelty(val_pos_all), 99.5))

    # ---- stage 2: fine-tuned CNN
    print("\nTraining the fine-tuned CNN gate...", flush=True)
    n_single = len(train_var_img) - 1500  # the last 1500 variants are branch-like clusters
    # Damaged calamansi leaves are the hard positives: their spots, holes and discolouration
    # resemble the diseased leaves among the negatives (citrus canker, black spot, PlantVillage
    # diseases), which are weighted x3. Without matching weight the gate learned "visible
    # damage = not calamansi" and rejected severely damaged calamansi photos.
    damaged_train = [p for p, lab in zip(pos["train"], pos_labels["train"]) if lab == "Damaged"]
    r_aug = random.Random(SEED + 30)
    damaged_aug = np.stack([np.asarray(augment(Image.fromarray(load_image(p)), r_aug)) for p in damaged_train for _ in range(2)])
    cnn_pos_train = np.concatenate([load_all(pos["train"]), damaged_aug,
                                    train_var_img[rng.sample(range(n_single), 1800)],
                                    train_var_img[n_single + np.array(rng.sample(range(1500), 1000))]])
    pos_w = np.r_[[3.0 if lab == "Damaged" else 1.5 for lab in pos_labels["train"]],
                  np.full(len(damaged_aug), 2.0), np.ones(2800)].astype(np.float32)
    hard = ("other_citrus_leaves", "other_citrus_leaves_plantvillage", "citrus_fruits", "lemon_leaves", "orange_leaves_hlb")
    neg_paths, neg_w = [], []
    for c in trained_on:
        ps = neg_split[c]["train"]
        ps = ps if c in hard else rng.sample(ps, min(len(ps), 450))
        neg_paths += ps
        neg_w += [3.0 if c in hard else 1.0] * len(ps)
    cnn_neg_train = np.concatenate([load_all(neg_paths), empty["train"]])
    neg_w += [2.0] * len(empty["train"])
    neg_val_paths = [p for c in trained_on for p in neg_split[c]["val"]]
    cnn_path = MODELS_DIR / ("leaf_gate_cnn.keras" if not unseen else "leaf_gate_cnn_unseen_experiment.keras")
    cnn = train_cnn(cnn_pos_train, pos_w, cnn_neg_train, np.array(neg_w, np.float32),
                    np.concatenate([load_all(pos["val"]), val_var_img]),
                    np.concatenate([load_all(neg_val_paths), empty["val"]]),
                    cnn_path, args.epochs_head, args.epochs_finetune)
    del cnn_pos_train, cnn_neg_train

    S_pos = {s: cnn_scores(cnn, load_all(pos[s])) for s in ("val", "test")}
    S_var = {"val": cnn_scores(cnn, val_var_img), "test": cnn_scores(cnn, test_var_img)}
    test_cluster = feats(test_cluster_img)
    S_cluster = cnn_scores(cnn, test_cluster_img)
    S_neg = {c: {s: cnn_scores(cnn, load_all(neg_split[c][s])) for s in ("val", "test")} for c in neg_split}
    S_neg["empty_backgrounds"] = {s: cnn_scores(cnn, empty[s]) for s in ("val", "test")}

    # ---- joint calibration on validation: keep >= 98% of calamansi validation images
    stage1_val = gate.accept(val_pos_all)
    cnn_val = np.r_[S_pos["val"], S_var["val"]]
    candidates = np.unique(np.r_[0.0, cnn_val])
    # Keep >= 98% of all calamansi validation images AND >= 98% of the validation photos of
    # EACH class, so the check cannot be tuned to healthy leaves at the expense of damaged ones.
    n_photo = len(S_pos["val"])
    val_lab = np.array(pos_labels["val"])

    def keeps(t: float) -> bool:
        ok = stage1_val & (cnn_val >= t)
        return ok.mean() >= 0.98 and all(ok[:n_photo][val_lab == c].mean() >= 0.98 for c in CLASS_NAMES)

    t_cnn = max(t for t in candidates if keeps(t))

    def accept(c_feats: np.ndarray, c_cnn: np.ndarray) -> np.ndarray:
        return gate.accept(c_feats) & (c_cnn >= t_cnn) if len(c_feats) else np.zeros(0, bool)

    if not unseen:
        gate.save(GATE_PATH)
        with np.load(GATE_PATH) as z:  # add the CNN threshold to the saved gate
            arrays = dict(z)
        np.savez_compressed(GATE_PATH, **arrays, t_cnn=np.float32(t_cnn))

    def rate(a: np.ndarray):
        return round(float(a.mean()), 4) if len(a) else None

    test_labels = np.array(pos_labels["test"])
    acc_test = accept(P["test"], S_pos["test"])
    stage1_only = {c: round(float(1 - gate.accept(N[c]["test"]).mean()), 4) for c in N if len(N[c]["test"])}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "stage 1: logistic regression + novelty distance on frozen ImageNet MobileNetV2 features; "
                  "stage 2: fine-tuned MobileNetV2 binary classifier; an image is accepted only if all checks pass",
        "regularisation_C": best[1],
        "thresholds": {"stage1_probability": round(gate.t_prob, 4), "stage1_novelty_distance": round(gate.t_dist, 4),
                       "stage2_cnn_probability": round(float(t_cnn), 4)},
        "calamansi_test_acceptance": {
            "all_photos": rate(acc_test),
            **{c: rate(acc_test[test_labels == c]) for c in CLASS_NAMES},
            "n": int(len(acc_test)),
            "on_new_backgrounds": rate(accept(test_var, S_var["test"])),
            "n_new_backgrounds": int(len(test_var)),
            "branch_like_clusters": rate(accept(test_cluster, S_cluster)),
            "n_branch_like_clusters": int(len(test_cluster)),
        },
        "negative_test_rejection": {c: {"rejected": round(1 - rate(accept(N[c]["test"], S_neg[c]["test"])), 4),
                                        "n": int(len(N[c]["test"]))} for c in N if len(N[c]["test"])},
        "stage1_only_test_rejection": stage1_only,
    }
    if unseen:
        report["unseen_categories"] = unseen
        out = OUTPUTS_DIR / "gate_unseen_experiment.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({c: report["negative_test_rejection"][c] for c in unseen}, indent=2))
        print("calamansi accepted:", report["calamansi_test_acceptance"])
        print(f"Wrote {out} (experiment only; the production gate was not changed)")
        return

    # ---- leave-one-dataset-out for stage 1 (cheap to retrain); the full gate is
    # tested on unseen categories with `--unseen` (retrains the CNN).
    loso = {}
    for c in N:
        if not len(N[c]["test"]):
            continue
        g = Gate(C=best[1]).fit(train_pos, neg_of("train", [c]))
        g.t_prob = float(np.quantile(g.prob(val_pos_all), 0.005))
        g.t_dist = float(np.percentile(g.novelty(val_pos_all), 99.5))
        loso[c] = {"stage1_rejected_when_unseen": round(float(1 - g.accept(N[c]["test"]).mean()), 4)}
    report["leave_one_dataset_out_stage1"] = loso
    report["train_counts"] = {"calamansi_photos": len(pos["train"]), "calamansi_variants": int(len(train_var)),
                              **{c: int(len(N[c]["train"])) for c in N}}
    unseen_file = OUTPUTS_DIR / "gate_unseen_experiment.json"
    if unseen_file.exists():  # results of an earlier `--unseen` run, shown alongside
        ex = json.loads(unseen_file.read_text(encoding="utf-8"))
        report["unseen_experiment"] = {
            "description": "Whole gate (both stages) retrained without these categories, then tested on their held-out images",
            "unseen_categories": ex["unseen_categories"],
            "rejected_when_unseen": {c: ex["negative_test_rejection"][c] for c in ex["unseen_categories"]},
            "calamansi_test_acceptance": ex["calamansi_test_acceptance"],
        }

    (OUTPUTS_DIR / "gate_evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    meta = {"created_at": report["generated_at"], "thresholds": report["thresholds"],
            "calamansi_test_acceptance": report["calamansi_test_acceptance"]["all_photos"],
            "negative_categories": list(N)}
    (MODELS_DIR / "leaf_gate.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\nCalamansi test images accepted:", report["calamansi_test_acceptance"])
    for c, v in report["negative_test_rejection"].items():
        print(f"  {c:34s} rejected {v['rejected']:.3f}  (stage 1 alone {stage1_only[c]:.3f}, n={v['n']})")
    print(f"Wrote {GATE_PATH}, {cnn_path.name}, {GATE_EXTRACTOR_PATH.name} and outputs/gate_evaluation.json")


if __name__ == "__main__":
    main()
