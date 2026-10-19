"""End-to-end API tests against the real trained models.

Detections are stored in a temporary local SQLite store, never in Supabase, so
running them does not touch the production detection log. Accounts are real
throw-away Supabase test users (deleted afterwards), because every detection
endpoint requires a signed-in, verified user.

Run from the backend folder:
    python -m pytest -q
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["DB_BACKEND"] = "local"
os.environ["LOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="calamansi_test_")

import main  # noqa: E402
import predict  # noqa: E402
from helpers import BrowserLikeClient, delete_test_accounts, signed_in  # noqa: E402
from config import DATASET_DIR, SPLITS_CSV  # noqa: E402
from download_ood_data import OOD_DIR  # noqa: E402


def jpeg_bytes(path: Path) -> bytes:
    buf = io.BytesIO()
    Image.open(path).convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


def held_out_images(label: str, n: int = 3) -> list[Path]:
    rows = [line.split(",") for line in SPLITS_CSV.read_text(encoding="utf-8").splitlines()[1:]]
    return [DATASET_DIR / r[0] for r in rows if r[1] == label and r[2] == "test"][:n]


def first_images(folder: Path, n: int) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png"}
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in exts)[:n] if folder.exists() else []


@pytest.fixture(scope="module")
def client():
    """Signed in as an ordinary verified user."""
    with BrowserLikeClient(main.app):  # runs the app's startup (loads the models) once
        c, _ = signed_in(main.app, "api")
        yield c
    delete_test_accounts()


def upload(client, data: bytes, name="leaf.jpg", ctype="image/jpeg"):
    return client.post("/api/predict", files={"file": (name, data, ctype)})


def test_health_reports_models_and_local_store(client):
    h = client.get("/api/health").json()
    assert h["model"]["loaded"] is True
    assert h["leaf_check"]["loaded"] is True
    assert h["database"] == {**h["database"], "backend": "local", "connected": True}


@pytest.mark.parametrize("label", ["Healthy", "Damaged"])
def test_calamansi_leaves_are_classified_and_saved(client, label):
    before = client.get("/api/stats").json()["total"]["total"]
    results = [upload(client, jpeg_bytes(p)) for p in held_out_images(label)]
    assert all(r.status_code == 201 for r in results), [r.json() for r in results]
    body = results[0].json()
    assert body["predicted_class"] in ("Healthy", "Damaged") and 0.5 <= body["confidence"] <= 1
    assert sum(r.json()["predicted_class"] == label for r in results) >= 2  # model agrees on most
    assert client.get("/api/stats").json()["total"]["total"] == before + len(results)
    assert client.get(f"/api/detections/{body['id']}").json()["id"] == body["id"]


@pytest.mark.parametrize("folder,n", [
    ("citrus_leaves/files/Citrus/Leaves", 4),
    ("citrus_leaves/files/Citrus/Fruits", 3),
    ("plant_village/files", 4),
    ("lfw/files", 3),
    ("imagenette/files", 3),
])
def test_non_calamansi_images_are_rejected_and_not_saved(client, folder, n):
    imgs = first_images(OOD_DIR / folder, 400)[::100][:n] or pytest.skip(f"{folder} not downloaded")
    before = client.get("/api/stats").json()["total"]["total"]
    for p in imgs:
        r = upload(client, jpeg_bytes(p), name=p.name)
        assert r.status_code == 422, (p, r.json())
        assert r.json()["detail"]["code"] == "not_calamansi_leaf"
        assert r.json()["detail"]["message"] == predict.INVALID_IMAGE_MESSAGE
    assert client.get("/api/stats").json()["total"]["total"] == before


def test_synthetic_non_leaf_images_are_rejected(client):
    rng = np.random.default_rng(0)
    noise = Image.fromarray(rng.integers(0, 255, (300, 300, 3), dtype=np.uint8))
    blue = Image.new("RGB", (300, 300), (40, 70, 200))  # the empty photo backdrop, no leaf
    green = Image.new("RGB", (600, 600), (60, 140, 50))  # leaf-coloured but no leaf
    white = Image.new("RGB", (600, 600), (250, 250, 250))
    big_noise = Image.fromarray(rng.integers(0, 255, (900, 900, 3), dtype=np.uint8))  # large enough for region analysis
    for img in (noise, blue, green, white, big_noise):
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        r = upload(client, buf.getvalue())
        assert r.status_code == 422 and r.json()["detail"]["code"] == "not_calamansi_leaf"


def test_lemon_leaf_photo_regression(client):
    """The stock photo of a lemon leaf on white that was once accepted as a Healthy calamansi leaf."""
    photo = Path(__file__).resolve().parents[1] / "regression_cases" / "lemon_leaf_user_upload.jpg"
    r = upload(client, photo.read_bytes(), photo.name)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_calamansi_leaf"
    assert "predicted_class" not in r.json()


def test_blurred_calamansi_photo_is_not_guessed(client):
    """Too blurry to tell calamansi from lemon or lime: rejected with its own reason, never labelled."""
    from PIL import ImageFilter
    img = Image.open(held_out_images("Healthy", 1)[0]).convert("RGB")
    buf = io.BytesIO()
    img.filter(ImageFilter.GaussianBlur(4 * max(img.size) / 640)).save(buf, "JPEG", quality=92)
    r = upload(client, buf.getvalue())
    assert r.status_code == 422 and "blurry" in r.json()["detail"]["reason"]


def test_upload_validation(client):
    assert upload(client, b"not an image", "x.txt", "text/plain").status_code == 415
    assert upload(client, b"not an image").status_code == 422
    assert upload(client, b"").status_code == 400
    # No or generic type (e.g. a JPEG saved as .jfif): accepted only because the content is a real image.
    leaf = jpeg_bytes(held_out_images("Healthy", 1)[0])
    assert upload(client, leaf, "leaf.jfif", "application/octet-stream").status_code == 201
    assert upload(client, b"not an image", "x.jfif", "application/octet-stream").status_code == 422


def test_detection_queries(client):
    page = client.get("/api/detections", params={"page_size": 2}).json()
    assert page["page_size"] == 2 and len(page["items"]) <= 2
    assert client.get("/api/detections", params={"predicted_class": "Other"}).status_code == 422
    assert client.get("/api/reports", params={"date_from": "2026-10-10", "date_to": "2026-10-01"}).status_code == 400
    assert client.get("/api/detections/00000000-0000-0000-0000-000000000000").status_code == 404


def test_requests_without_a_session_are_rejected(client):
    anon = BrowserLikeClient(main.app)
    anon.get("/api/auth/csrf")
    leaf = jpeg_bytes(held_out_images("Healthy", 1)[0])
    assert anon.post("/api/predict", files={"file": ("leaf.jpg", leaf, "image/jpeg")}).status_code == 401
    for path in ("/api/detections", "/api/stats", "/api/reports", "/api/reports/export"):
        assert anon.get(path).status_code == 401, path
    assert anon.get("/api/health").status_code == 200  # public status only
    no_csrf = BrowserLikeClient(main.app)
    assert no_csrf.post("/api/predict", files={"file": ("leaf.jpg", leaf, "image/jpeg")}).status_code == 403


def test_users_only_see_their_own_detections_and_admins_see_all(client):
    leaf = jpeg_bytes(held_out_images("Damaged", 1)[0])
    mine = client.post("/api/predict", files={"file": ("mine.jpg", leaf, "image/jpeg")}).json()
    other, _ = signed_in(main.app, "other")
    assert other.get(f"/api/detections/{mine['id']}").status_code == 404
    assert all(d["id"] != mine["id"] for d in other.get("/api/detections", params={"page_size": 100}).json()["items"])
    assert other.get("/api/stats").json()["total"]["total"] == 0
    assert other.get(f"/api/images/{mine['image_path']}").status_code == 404
    assert client.get(f"/api/images/{mine['image_path']}").status_code == 200
    admin, _ = signed_in(main.app, "admin", admin=True)
    assert admin.get(f"/api/detections/{mine['id']}").status_code == 200
    assert admin.get("/api/admin/users").status_code == 200
    assert other.get("/api/admin/users").status_code == 403


def test_frontend_routes_and_caching(client):
    dist = BACKEND.parent / "frontend" / "dist"
    if not (dist / "index.html").exists():
        pytest.skip("frontend not built")
    for route in ("/", "/login", "/register", "/app", "/app/logs", "/app/logs/some-id"):
        r = client.get(route)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert r.headers["cache-control"] == "no-cache"
    asset = next((dist / "assets").glob("*.js")).name
    assert "immutable" in client.get(f"/assets/{asset}").headers["cache-control"]
    assert client.get("/assets/old-build-123.js").status_code == 404  # never HTML for a missing script
    assert client.get("/api/unknown").status_code == 404
