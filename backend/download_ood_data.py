"""Download the public "not a calamansi leaf" image sets used by train_gate.py.

The calamansi dataset only contains calamansi leaves, so on its own it cannot
teach a model what to reject. These public datasets provide negative examples:

  citrus_leaves  other citrus (orange) leaves                       ~60 MB
  plant_village  isolated leaves of 14 crop species, incl. orange   ~870 MB
  tf_flowers     flower photos                                      ~230 MB
  imagenette     10 everyday ImageNet classes (dogs, trucks, ...)   ~100 MB
  caltech101     101 object categories                              ~140 MB
  lfw            photos of people's faces                           ~180 MB

Species-labelled single citrus leaves (hard negatives: look most like calamansi), CC BY 4.0:
  lemon_bd       BDLemonLeaf, lemon (Citrus limon) leaves, Dhaka   ~100 MB
                 doi:10.17632/643f5bbc2t.6
  lemon_jamalpur lemon leaves, Melandaha, Jamalpur (original set)  ~360 MB
                 doi:10.17632/44nrn4593f.1
  orange_hlb     orange leaves (healthy / HLB), Mexico, background
                 removed                                           ~1.5 GB
                 doi:10.17632/jgkh2jxbwt.1

Each set goes into backend/ood_data/<name>/files/. Already-downloaded sets are
skipped, so the script can be re-run after an interruption.

Usage:
    python download_ood_data.py              # all sets
    python download_ood_data.py beans lfw    # only some
"""
from __future__ import annotations

import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from config import BACKEND_DIR

OOD_DIR = BACKEND_DIR / "ood_data"

SOURCES = {
    "citrus_leaves": ("https://data.mendeley.com/public-files/datasets/3f83gxmv57/files/"
                      "53398b67-6f0e-4a67-8384-e2b574b2ebf4/file_downloaded", "zip"),
    "plant_village": ("https://data.mendeley.com/public-files/datasets/tywbtsjrjv/files/"
                      "d5652a28-c1d8-4b76-97f3-72fb80f94efc/file_downloaded", "zip"),
    "tf_flowers": ("http://download.tensorflow.org/example_images/flower_photos.tgz", "tgz"),
    "imagenette": ("https://s3.amazonaws.com/fast-ai-imageclas/imagenette2-160.tgz", "tgz"),
    "caltech101": ("https://data.caltech.edu/records/mzrjq-6wc02/files/caltech-101.zip?download=1", "zip"),
    "lfw": ("https://ndownloader.figshare.com/files/5976018", "tgz"),
    "lemon_bd": ("https://data.mendeley.com/public-files/datasets/643f5bbc2t/files/"
                 "7cf6f28b-637c-4db4-9086-5b297d8a2f55/file_downloaded", "zip"),
    "lemon_jamalpur": ("https://data.mendeley.com/public-files/datasets/44nrn4593f/files/"
                       "4d8bb0c8-2371-4de4-9158-08af70a347a0/file_downloaded", "zip"),
    "orange_hlb": ("https://data.mendeley.com/public-files/datasets/jgkh2jxbwt/files/"
                   "42c44990-bc2e-44f6-8ea8-0618403612b9/file_downloaded", "zip"),
}


def _safe_extract(archive: Path, kind: str, dest: Path) -> None:
    """Extract without allowing paths that escape `dest` (zip-slip)."""
    root = dest.resolve()
    if kind == "zip":
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():
                if root not in (dest / m).resolve().parents and (dest / m).resolve() != root:
                    raise RuntimeError(f"Unsafe path in archive: {m}")
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")
    # Some archives contain nested archives (e.g. caltech101 -> 101_ObjectCategories.tar.gz).
    # macOS "._name" metadata files and __MACOSX folders are not real archives/images.
    for junk in [p for p in dest.rglob("*") if p.name.startswith("._") or p.name == "__MACOSX"]:
        shutil.rmtree(junk) if junk.is_dir() else junk.unlink(missing_ok=True)
    for inner in list(dest.rglob("*.tar.gz")) + list(dest.rglob("*.tgz")) + list(dest.rglob("*.zip")):
        sub = inner.with_suffix("").with_suffix("") if inner.name.endswith(".tar.gz") else inner.with_suffix("")
        sub.mkdir(exist_ok=True)
        _safe_extract(inner, "zip" if inner.suffix == ".zip" else "tgz", sub)
        inner.unlink()


def download(name: str) -> None:
    url, kind = SOURCES[name]
    folder = OOD_DIR / name
    files = folder / "files"
    if (folder / "extracted.done").exists():
        print(f"{name}: already present ({sum(1 for _ in files.rglob('*') if _.is_file())} files)")
        return
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / f"download.{kind}"
    print(f"{name}: downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(archive, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    print(f"{name}: extracting")
    if files.exists():
        shutil.rmtree(files)
    files.mkdir()
    _safe_extract(archive, kind, files)
    archive.unlink()
    (folder / "extracted.done").touch()
    print(f"{name}: done ({sum(1 for _ in files.rglob('*') if _.is_file())} files)")


def main() -> None:
    names = sys.argv[1:] or list(SOURCES)
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise SystemExit(f"Unknown dataset(s): {unknown}. Choose from {list(SOURCES)}")
    for n in names:
        try:
            download(n)
        except Exception as e:  # keep going; report at the end
            print(f"{n}: FAILED - {e}")


if __name__ == "__main__":
    main()
