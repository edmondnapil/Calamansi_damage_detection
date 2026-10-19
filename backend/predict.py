"""Load the trained models and classify calamansi leaf images.

Every image goes through two steps:

  1. Calamansi-leaf gate (train_gate.py): is this a photo of a calamansi leaf
     at all? If not, the image is rejected and NOT classified.
  2. Healthy / Damaged classifier (train_model.py), only for accepted images.

The same `load_image` function is used by train_model.py, evaluate_model.py,
train_gate.py and the FastAPI server, so preprocessing is identical everywhere:

    decode -> apply EXIF rotation -> RGB -> resize to 224x224 (bilinear) -> uint8

Normalisation (e.g. scaling to [-1, 1] for MobileNetV2) is built into the
saved models themselves, so callers only pass raw 0-255 pixels.

CLI usage:
    python predict.py path\\to\\leaf.jpg [more.jpg ...]
"""
from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from config import CLASS_NAMES, IMG_SIZE, METADATA_PATH, MODELS_DIR

GATE_PATH = MODELS_DIR / "leaf_gate.npz"
GATE_EXTRACTOR_PATH = MODELS_DIR / "leaf_gate_extractor.keras"
GATE_CNN_PATH = MODELS_DIR / "leaf_gate_cnn.keras"
# Second, general check (the earlier gate, best at rejecting objects, flowers, people, other plants).
# An image must pass BOTH: the species check above (also trained on lemon/orange leaves) and this one.
GENERAL_GATE_PREFIX = "leaf_gate_general"
GATE_CONFIG_PATH = MODELS_DIR / "leaf_gate_config.json"
INVALID_IMAGE_MESSAGE = "Invalid Image: This image could not be verified as a calamansi leaf. Please upload a clear photo of a calamansi leaf."
# A photo that is not recognised as a whole is accepted only if at least this many regions of it
# are recognised as calamansi leaves (one stray match is not enough), and at least the share in
# leaf_gate_config.json ("min_region_fraction", chosen on validation data, see calibrate_gate.py):
# a few zoomed-in windows of a lemon leaf can resemble calamansi, a real calamansi branch fills many.
MIN_LEAF_REGIONS = 2


class ModelNotAvailableError(RuntimeError):
    """Raised when no trained model has been saved yet."""


class InvalidImageError(ValueError):
    """Raised when the uploaded bytes are not a decodable image."""


def load_image(source: str | Path | bytes, size: int = IMG_SIZE) -> np.ndarray:
    """Return a (size, size, 3) uint8 array, preprocessed exactly as in training."""
    img = pad_to_square(open_image(source)).resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


def open_image(source: str | Path | bytes) -> Image.Image:
    """Decode, apply EXIF rotation and convert to RGB (full resolution)."""
    try:
        img = Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)
        return ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise InvalidImageError(f"Could not read image: {e}") from e


def sharpness(img: Image.Image) -> float:
    """Variance of the Laplacian of the grayscale photo at a 512 px long side.
    Sharp photos score >= ~30 (phone photos usually hundreds); 2-4 px blur scores <= ~4."""
    g = img.convert("L")
    g.thumbnail((512, 512))
    a = np.asarray(g, np.float32)
    lap = 4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]
    return float(lap.var())


def leaf_regions(img: Image.Image, size: int = IMG_SIZE, max_regions: int = 16) -> list[np.ndarray]:
    """Overlapping square windows (50% and 70% of the short side, 50% overlap).

    Used when the photo as a whole is not recognised, e.g. a branch with many
    leaves and fruit: individual windows then show one or a few leaves, which
    is what the models were trained on. Windows smaller than the model input
    (224 px) are skipped, so small photos are only judged as a whole.
    """
    w, h = img.size
    out = []
    for frac in (0.5, 0.7):
        side = int(min(w, h) * frac)
        if side < size:
            continue  # smaller than the model input: it would only be a blurry enlargement
        step = max(1, side // 2)
        xs = list(range(0, max(1, w - side) + 1, step)) or [0]
        ys = list(range(0, max(1, h - side) + 1, step)) or [0]
        for y in ys:
            for x in xs:
                window = img.crop((x, y, x + side, y + side)).resize((size, size), Image.Resampling.BILINEAR)
                out.append(np.asarray(window))
    if len(out) > max_regions:  # keep an even spread over the photo
        out = [out[i] for i in np.linspace(0, len(out) - 1, max_regions).round().astype(int)]
    return out


def pad_to_square(img: Image.Image) -> Image.Image:
    """Pad a non-square photo to a square with its own border colour.

    Squashing a 3:4 phone photo into a square distorts leaf shapes, and the
    models were trained on square photos only, so the leaf is kept undistorted.
    Square images (all training photos) are returned unchanged.
    """
    w, h = img.size
    if w == h:
        return img
    a = np.asarray(img)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    colour = tuple(int(v) for v in np.median(border, axis=0))
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), colour)
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas


@dataclass
class GateResult:
    is_calamansi_leaf: bool
    score: float               # fine-tuned gate CNN: probability that this is a calamansi leaf
    novelty: float             # distance to the nearest calamansi training example
    reason: str | None = None  # why it was rejected


class LeafGate:
    """Decides whether an image shows a calamansi leaf (see train_gate.py)."""

    def __init__(self, prefix: str = "leaf_gate"):
        gate_path, extractor_path, cnn_path = (MODELS_DIR / f"{prefix}.npz", MODELS_DIR / f"{prefix}_extractor.keras",
                                               MODELS_DIR / f"{prefix}_cnn.keras")
        if prefix == "leaf_gate":  # module constants may be redirected (e.g. evaluation of an older gate)
            gate_path, extractor_path, cnn_path = GATE_PATH, GATE_EXTRACTOR_PATH, GATE_CNN_PATH
        if not (gate_path.exists() and extractor_path.exists() and cnn_path.exists()):
            raise ModelNotAvailableError(
                "The calamansi-leaf validation model is missing, so images cannot be checked. "
                "Run `python download_ood_data.py` and `python train_gate.py` in the backend folder."
            )
        import tensorflow as tf

        self.extractor = tf.keras.models.load_model(extractor_path)
        self.cnn = tf.keras.models.load_model(cnn_path)
        g = np.load(gate_path)
        self.coef, self.intercept = g["coef"], float(g["intercept"])
        self.pca_mean, self.pca_components, self.bank = g["pca_mean"], g["pca_components"], g["bank"]
        self.t_prob, self.t_dist, self.t_cnn = float(g["t_prob"]), float(g["t_dist"]), float(g["t_cnn"])
        # Minimum sharpness (older gate files have none: no blur check).
        self.t_sharp = float(g["t_sharp"]) if "t_sharp" in g.files else 0.0

    def check(self, arr: np.ndarray) -> GateResult:
        return self.check_batch(arr[np.newaxis])[0]

    def check_batch(self, arrs: np.ndarray) -> list[GateResult]:
        x = arrs.astype(np.float32)
        f = self.extractor.predict(x, batch_size=32, verbose=0)
        f = f / np.linalg.norm(f, axis=1, keepdims=True)
        linear = 1 / (1 + np.exp(-(f @ self.coef + self.intercept)))
        z = (f - self.pca_mean) @ self.pca_components.T
        novelty = np.sqrt(((self.bank[None] - z[:, None]) ** 2).sum(-1).min(1))
        score = self.cnn.predict(x, batch_size=32, verbose=0).ravel()
        out = []
        for lin, nov, sc in zip(linear, novelty, score):
            if nov > self.t_dist:
                out.append(GateResult(False, float(sc), float(nov),
                                      "too different from every calamansi leaf the model was trained on"))
            elif lin < self.t_prob or sc < self.t_cnn:
                out.append(GateResult(False, float(sc), float(nov), "does not look like a calamansi leaf"))
            else:
                out.append(GateResult(True, float(sc), float(nov)))
        return out


class CombinedGate:
    """The calamansi-leaf check used by the app: the species check AND the general check.

    Each keeps its own thresholds (chosen on validation data when it was trained). Accepting only
    what both accept keeps the species check's rejection of lemon/orange leaves and the general
    check's rejection of objects, flowers and people. Also holds the blur and region settings."""

    def __init__(self, use_general: bool = True):
        self.species = LeafGate()
        general_ok = all((MODELS_DIR / f"{GENERAL_GATE_PREFIX}{ext}").exists()
                         for ext in (".npz", "_extractor.keras", "_cnn.keras"))
        self.general = LeafGate(GENERAL_GATE_PREFIX) if use_general and general_ok else None
        cfg = json.loads(GATE_CONFIG_PATH.read_text(encoding="utf-8")) if GATE_CONFIG_PATH.exists() else {}
        self.t_sharp = float(cfg.get("min_sharpness", self.species.t_sharp))
        self.min_region_fraction = float(cfg.get("min_region_fraction", 0.0))
        # attributes of the species check, for diagnostics (diagnose_dataset.stage_scores)
        for name in ("extractor", "cnn", "coef", "intercept", "pca_mean", "pca_components", "bank", "t_prob", "t_dist", "t_cnn"):
            setattr(self, name, getattr(self.species, name))

    def check(self, arr: np.ndarray) -> GateResult:
        return self.check_batch(arr[np.newaxis])[0]

    def check_batch(self, arrs: np.ndarray) -> list[GateResult]:
        a = self.species.check_batch(arrs)
        if not self.general:
            return a
        b = self.general.check_batch(arrs)
        return [x if not x.is_calamansi_leaf else y if not y.is_calamansi_leaf else
                GateResult(True, min(x.score, y.score), max(x.novelty, y.novelty)) for x, y in zip(a, b)]


@dataclass
class Prediction:
    predicted_class: str | None          # None when the image was rejected by the gate
    confidence: float | None              # probability of the predicted class, 0..1
    probabilities: dict[str, float]
    model_version: str
    gate: GateResult = field(default_factory=lambda: GateResult(True, 1.0, 0.0))
    analysis: str = "whole_photo"        # "whole_photo" or "leaf_regions"
    regions_used: int = 1                 # regions recognised as calamansi leaves (and classified)
    regions_checked: int = 1

    @property
    def accepted(self) -> bool:
        return self.gate.is_calamansi_leaf


class Predictor:
    """Wraps both saved models. Load once, call `predict_bytes` many times."""

    def __init__(self, metadata_path: Path = METADATA_PATH, require_gate: bool = True):
        if not metadata_path.exists():
            raise ModelNotAvailableError(
                "No trained model found. Run `python prepare_dataset.py` and "
                "`python train_model.py` in the backend folder first."
            )
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        model_file = MODELS_DIR / self.metadata["model_file"]
        if not model_file.exists():
            raise ModelNotAvailableError(f"Model file missing: {model_file}")

        import tensorflow as tf  # imported lazily: slow, and not needed for metadata-only callers

        self.model = tf.keras.models.load_model(model_file)
        # The web app never classifies without the gate: an unchecked image would always
        # get a label. Only offline evaluation of the classifier itself skips it.
        self.gate = CombinedGate() if require_gate else None
        self.class_names: list[str] = self.metadata.get("class_names", CLASS_NAMES)
        self.img_size: int = self.metadata.get("img_size", IMG_SIZE)
        self.threshold: float = self.metadata.get("threshold", 0.5)
        self.version: str = self.metadata["model_version"]

    def _classify(self, arrs: np.ndarray, weights: np.ndarray | None = None) -> tuple[str, float, dict[str, float]]:
        # Single sigmoid output = P(class_names[1]) = P("Healthy"). Several regions are
        # averaged, weighted by how clearly each one looks like a calamansi leaf.
        p = self.model.predict(arrs.astype(np.float32), batch_size=32, verbose=0).ravel()
        p1 = float(np.average(p, weights=weights))
        probs = {self.class_names[0]: 1.0 - p1, self.class_names[1]: p1}
        label = self.class_names[1] if p1 >= self.threshold else self.class_names[0]
        return label, probs[label], probs

    def predict_array(self, arr: np.ndarray) -> Prediction:
        """Classify an already preprocessed 224x224 image (whole photo only)."""
        gate = self.gate.check(arr) if self.gate else GateResult(True, 1.0, 0.0, "gate not used")
        if not gate.is_calamansi_leaf:
            return Prediction(None, None, {}, self.version, gate)
        label, conf, probs = self._classify(arr[np.newaxis])
        return Prediction(label, conf, probs, self.version, gate)

    def predict_image(self, img: Image.Image) -> Prediction:
        """Whole photo first; if not recognised, look for calamansi leaves in regions of it.

        A photo too blurry to verify the species is rejected first: blur removes the leaf details
        that tell calamansi from lemon or lime, so such a photo is not guessed."""
        if self.gate and self.gate.t_sharp and sharpness(img) < self.gate.t_sharp:
            return Prediction(None, None, {}, self.version,
                              GateResult(False, 0.0, 0.0, "too blurry to verify that it is a calamansi leaf"))
        whole = np.asarray(pad_to_square(img).resize((self.img_size, self.img_size), Image.Resampling.BILINEAR))
        result = self.predict_array(whole)
        if result.accepted or not self.gate:
            return result
        found = leaf_regions(img, self.img_size)
        if not found:  # photo too small to split into regions
            return result
        regions = np.stack(found)
        checks = self.gate.check_batch(regions)
        ok = [i for i, c in enumerate(checks) if c.is_calamansi_leaf]
        if len(ok) < MIN_LEAF_REGIONS or len(ok) < self.gate.min_region_fraction * len(regions):
            result.regions_checked, result.regions_used = len(regions) + 1, 0
            return result
        weights = np.array([checks[i].score for i in ok])
        label, conf, probs = self._classify(regions[ok], weights)
        gate = GateResult(True, float(weights.max()), float(min(checks[i].novelty for i in ok)))
        return Prediction(label, conf, probs, self.version, gate, "leaf_regions", len(ok), len(regions) + 1)

    def predict_bytes(self, data: bytes) -> Prediction:
        return self.predict_image(open_image(data))

    def predict_file(self, path: str | Path) -> Prediction:
        return self.predict_image(open_image(path))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    predictor = Predictor()
    for path in sys.argv[1:]:
        try:
            p = predictor.predict_file(path)
            if not p.accepted:
                print(f"{path}: REJECTED - {INVALID_IMAGE_MESSAGE} ({p.gate.reason}; "
                      f"gate score {p.gate.score:.3f}, novelty {p.gate.novelty:.2f})")
                continue
            print(f"{path}: {p.predicted_class} ({p.confidence:.1%})  "
                  f"[Healthy {p.probabilities['Healthy']:.3f} / Damaged {p.probabilities['Damaged']:.3f}]  "
                  f"gate score {p.gate.score:.3f}")
        except InvalidImageError as e:
            print(f"{path}: ERROR {e}")


if __name__ == "__main__":
    main()
