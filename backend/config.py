"""Shared configuration for training, evaluation and inference.

Every script imports its paths and constants from here so the training
pipeline and the web API can never drift apart (same image size, same
class order, same model file).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

# The original Roboflow export lives in the project root as train/ valid/ test/.
# Override with DATASET_DIR if the dataset is moved elsewhere.
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT))).resolve()

MODELS_DIR = BACKEND_DIR / "models"
OUTPUTS_DIR = BACKEND_DIR / "outputs"
MODELS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

MODEL_PATH = Path(os.getenv("MODEL_PATH", str(MODELS_DIR / "calamansi_mobilenetv2.keras")))
METADATA_PATH = MODELS_DIR / "model_metadata.json"
SPLITS_CSV = OUTPUTS_DIR / "splits.csv"
DATASET_REPORT = OUTPUTS_DIR / "dataset_report.json"
HISTORY_JSON = OUTPUTS_DIR / "training_history.json"
EVALUATION_JSON = OUTPUTS_DIR / "evaluation_metrics.json"

# Binary task. Index order is alphabetical and fixed: the model's single
# sigmoid output is P(class index 1) = P("Healthy").
CLASS_NAMES = ["Damaged", "Healthy"]
IMG_SIZE = 224
SEED = 42

SPLIT_NAMES = {"train": "train", "valid": "val", "val": "val", "validation": "val", "test": "test"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def normalize_class(name: str) -> str | None:
    """Map folder names like 'healthy' / 'DAMAGED' to the canonical labels."""
    lowered = name.strip().lower()
    for cls in CLASS_NAMES:
        if lowered == cls.lower():
            return cls
    return None
