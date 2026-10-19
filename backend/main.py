"""FastAPI backend for Web-Based Calamansi Leaf Damage Detection Using Image Classification.

Run (from the backend folder, with the virtual environment active):
    uvicorn main:app --reload --port 8000

Interactive API docs: http://localhost:8000/docs
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os

# Hide TensorFlow's start-up information messages (oneDNN, CPU instructions); errors still show.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image

from admin import router as admin_router
from admin import set_repository_provider
from auth import AUTH_ENABLED, CurrentUser, csrf_middleware, current_user
from auth import router as auth_router
from config import BACKEND_DIR, CLASS_NAMES, DATASET_REPORT, EVALUATION_JSON, METADATA_PATH, OUTPUTS_DIR
from predict import INVALID_IMAGE_MESSAGE, InvalidImageError, ModelNotAvailableError, Predictor
from storage import APP_TZ, LocalRepository, Repository, create_repository, daily_series

log = logging.getLogger("calamansi")
logging.basicConfig(level=logging.INFO)
# One line per Supabase request would flood the console; problems are still logged as warnings.
logging.getLogger("httpx").setLevel(logging.WARNING)

APP_TITLE = "Web-Based Calamansi Leaf Damage Detection Using Image Classification"
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "5"))
KEEP_IMAGES = os.getenv("KEEP_UPLOADED_IMAGES", "true").lower() in ("1", "true", "yes")
LOW_CONFIDENCE = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.70"))
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
GENERIC_TYPES = {None, "", "application/octet-stream", "image/jpg", "image/pjpeg"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO = multi-picture JPEG from some phone cameras
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs

state: dict = {"predictor": None, "model_error": None, "repo": None, "repo_error": None}
predict_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state["predictor"] = Predictor()
        log.info("Model loaded: %s", state["predictor"].version)
    except ModelNotAvailableError as e:
        state["model_error"] = str(e)
        log.warning("Model not available: %s", e)
    try:
        state["repo"] = create_repository()
        log.info("Storage backend: %s", state["repo"].backend)
    except Exception as e:
        state["repo_error"] = str(e)
        log.error("Storage backend failed: %s", e)
    yield


app = FastAPI(title=APP_TITLE, version="1.0.0", lifespan=lifespan)
app.middleware("http")(csrf_middleware)
app.include_router(auth_router)
app.include_router(admin_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    allow_credentials=True,
)


def repo() -> Repository:  # noqa: D401 (also used by admin.py, see set_repository_provider below)
    if state["repo"] is None:
        raise HTTPException(503, f"Database is not available: {state['repo_error']}")
    return state["repo"]


set_repository_provider(repo)


def predictor() -> Predictor:
    if state["predictor"] is None:
        raise HTTPException(503, state["model_error"] or "Model is not loaded.")
    return state["predictor"]


def owner_of(user: CurrentUser) -> str | None:
    """Records a request may see: administrators all, everyone else only their own."""
    return None if user.is_admin else user.id


def may_access(user: CurrentUser, record: dict) -> bool:
    return user.is_admin or record.get("user_id") == user.id


def read_json(path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def serialize(record: dict) -> dict:
    out = dict(record)
    out["confidence"] = float(out["confidence"])
    for k in ("prob_healthy", "prob_damaged"):
        if out.get(k) is not None:
            out[k] = float(out[k])
    out.setdefault("image_url", None)
    return out


# --------------------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    p = state["predictor"]
    db = state["repo"].status() if state["repo"] else {"backend": "none", "connected": False,
                                                       "error": state["repo_error"]}
    return {
        "status": "ok" if p and db.get("connected") else "degraded",
        "app": APP_TITLE,
        "model": {"loaded": p is not None, "version": p.version if p else None,
                  "architecture": p.metadata.get("architecture") if p else None, "error": state["model_error"]},
        # The Healthy/Damaged model only runs on images this check accepts.
        "leaf_check": {"loaded": bool(p and p.gate)},
        "database": db,
        "auth": {"enabled": AUTH_ENABLED},
        "image_retention": KEEP_IMAGES,
        "max_upload_mb": MAX_UPLOAD_MB,
        "timezone": str(APP_TZ),
    }


@app.post("/api/predict", status_code=201)
async def predict(file: UploadFile = File(..., description="Calamansi leaf photo (JPG, PNG or WEBP)"),
                  user: CurrentUser = Depends(current_user)):
    model = predictor()
    store = repo()

    # Browsers report no type or a generic one for some real images (e.g. a JPEG saved as .jfif);
    # those are accepted here because the image content itself is verified below.
    if file.content_type not in ALLOWED_TYPES | GENERIC_TYPES:
        raise HTTPException(415, f"Unsupported file type '{file.content_type}'. Upload a JPG, PNG or WEBP image.")
    data = await file.read(int(MAX_UPLOAD_MB * 1024 * 1024) + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Image is larger than {MAX_UPLOAD_MB:g} MB.")
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise HTTPException(415, f"Image content is {probe.format}, not JPG/PNG/WEBP.")
            probe.verify()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "The file could not be read as an image. It may be corrupted.")

    try:
        with predict_lock:
            result = model.predict_bytes(data)
    except InvalidImageError as e:
        raise HTTPException(422, str(e))

    if not result.accepted:
        # Not a calamansi leaf: no Healthy/Damaged label, no confidence, nothing saved.
        log.info("Rejected upload %r: %s (gate score %.3f, novelty %.2f; %d regions checked)", file.filename,
                 result.gate.reason, result.gate.score, result.gate.novelty, result.regions_checked)
        raise HTTPException(422, {"code": "not_calamansi_leaf", "message": INVALID_IMAGE_MESSAGE,
                                  "reason": result.gate.reason, "regions_checked": result.regions_checked})

    created = datetime.now(timezone.utc)
    image_path, warning = None, None
    if KEEP_IMAGES:
        try:
            image_path = store.save_image(_reencode_jpeg(data), created)
        except Exception as e:
            log.exception("Image upload failed")
            warning = f"Prediction saved without the image (storage upload failed: {str(e)[:120]})"

    record = {
        "predicted_class": result.predicted_class,
        "confidence": round(result.confidence, 6),
        "prob_healthy": round(result.probabilities["Healthy"], 6),
        "prob_damaged": round(result.probabilities["Damaged"], 6),
        "image_path": image_path,
        "original_filename": (file.filename or "upload")[:255],
        "model_version": result.model_version,
        "user_id": user.id,  # always the signed-in user, never a value sent by the browser
    }
    try:
        saved = store.insert(record)
    except Exception as e:
        log.exception("Database insert failed")
        raise HTTPException(502, f"The model classified the image as {result.predicted_class} "
                                 f"({result.confidence:.1%}), but saving to the database failed: {str(e)[:160]}")

    out = serialize(store.with_image_urls([saved])[0])
    out["low_confidence"] = result.confidence < LOW_CONFIDENCE
    # "leaf_regions": the photo as a whole was not one leaf (e.g. a branch with fruit), so the
    # result combines the regions of it that were recognised as calamansi leaves.
    out["analysis"] = result.analysis
    out["regions_used"] = result.regions_used
    out["regions_checked"] = result.regions_checked
    out["warning"] = warning
    return out


@app.get("/api/detections")
def list_detections(
    search: str | None = Query(None, max_length=100),
    predicted_class: Literal["Healthy", "Damaged"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: CurrentUser = Depends(current_user),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from must be on or before date_to.")
    store = repo()
    items, total = store.list(search=search, predicted_class=predicted_class, date_from=date_from,
                              date_to=date_to, offset=(page - 1) * page_size, limit=page_size, owner=owner_of(user))
    return {"items": [serialize(i) for i in store.with_image_urls(items)], "total": total,
            "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size))}


@app.get("/api/detections/{detection_id}")
def get_detection(detection_id: UUID, user: CurrentUser = Depends(current_user)):
    store = repo()
    record = store.get(str(detection_id))
    if not record or not may_access(user, record):  # 404, not 403: do not reveal other users' records
        raise HTTPException(404, "Detection not found.")
    return serialize(store.with_image_urls([record])[0])


@app.get("/api/stats")
def stats(days: int = Query(7, ge=1, le=365), user: CurrentUser = Depends(current_user)):
    """All-time totals plus this period vs. the previous period of equal length."""
    store, owner = repo(), owner_of(user)
    today = datetime.now(APP_TZ).date()
    cur_from, prev_from, prev_to = today - timedelta(days=days - 1), today - timedelta(days=2 * days - 1), \
        today - timedelta(days=days)

    # 4 independent queries, sent in parallel (previously 10 sequential round trips,
    # ~3.5 s against Supabase, which left the dashboard cards empty while loading).
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_healthy = pool.submit(store.count, "Healthy", owner=owner)
        f_damaged = pool.submit(store.count, "Damaged", owner=owner)
        f_rows = pool.submit(store.rows_between, prev_from, today, owner=owner)
        f_latest = pool.submit(store.list, search=None, predicted_class=None, date_from=None, date_to=None,
                               offset=0, limit=1, owner=owner)
        totals = {"Healthy": f_healthy.result(), "Damaged": f_damaged.result()}
        rows, (latest, _) = f_rows.result(), f_latest.result()

    def local_day(r) -> date:
        return datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")).astimezone(APP_TZ).date()

    days_of = [(local_day(r), r["predicted_class"]) for r in rows]

    def block(cls=None):
        match = [d for d, c in days_of if cls is None or c == cls]
        cur = sum(cur_from <= d <= today for d in match)
        prev = sum(prev_from <= d <= prev_to for d in match)
        change = None if prev == 0 else round((cur - prev) / prev * 100, 1)
        total = sum(totals.values()) if cls is None else totals[cls]
        return {"total": total, "period": cur, "previous_period": prev, "change_pct": change}

    return {
        "days": days,
        "total": block(),
        "healthy": block("Healthy"),
        "damaged": block("Damaged"),
        "latest": serialize(store.with_image_urls(latest)[0]) if latest else None,
    }


def _report_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = datetime.now(APP_TZ).date()
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=6)
    if date_from > date_to:
        raise HTTPException(400, "date_from must be on or before date_to.")
    if (date_to - date_from).days > 366:
        raise HTTPException(400, "Date range is limited to one year.")
    return date_from, date_to


@app.get("/api/reports")
def reports(date_from: date | None = None, date_to: date | None = None, user: CurrentUser = Depends(current_user)):
    date_from, date_to = _report_range(date_from, date_to)
    rows = repo().rows_between(date_from, date_to, owner=owner_of(user))
    by_class = {c: [float(r["confidence"]) for r in rows if r["predicted_class"] == c] for c in CLASS_NAMES}
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "total": len(rows),
        "counts": {c: len(v) for c, v in by_class.items()},
        "average_confidence": {c: (round(sum(v) / len(v), 4) if v else None) for c, v in by_class.items()},
        "low_confidence_count": sum(1 for r in rows if float(r["confidence"]) < LOW_CONFIDENCE),
        "daily": daily_series(rows, date_from, date_to),
    }


@app.get("/api/reports/export")
def export_csv(date_from: date | None = None, date_to: date | None = None,
               predicted_class: Literal["Healthy", "Damaged"] | None = None,
               user: CurrentUser = Depends(current_user)):
    date_from, date_to = _report_range(date_from, date_to)
    store, items, offset = repo(), [], 0
    while True:
        batch, total = store.list(search=None, predicted_class=predicted_class, date_from=date_from,
                                  date_to=date_to, offset=offset, limit=100, owner=owner_of(user))
        items += batch
        offset += 100
        if offset >= total or not batch:
            break
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "created_at_local", "predicted_class", "confidence_pct", "prob_healthy", "prob_damaged",
                "original_filename", "model_version"])
    for i in items:
        ts = datetime.fromisoformat(str(i["created_at"]).replace("Z", "+00:00")).astimezone(APP_TZ)
        w.writerow([i["id"], ts.strftime("%Y-%m-%d %H:%M:%S"), i["predicted_class"],
                    f"{float(i['confidence']) * 100:.2f}", i.get("prob_healthy"), i.get("prob_damaged"),
                    i.get("original_filename"), i["model_version"]])
    name = f"calamansi_detections_{date_from}_{date_to}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/model")
def model_info():
    """Model metadata and offline evaluation metrics (not live application statistics)."""
    meta = read_json(METADATA_PATH)
    evaluation = read_json(EVALUATION_JSON)
    dataset = read_json(DATASET_REPORT)
    gate = read_json(OUTPUTS_DIR / "gate_evaluation.json")
    return {
        "metadata": meta,
        "evaluation": evaluation,
        "dataset": {k: dataset.get(k) for k in ("unique_source_photos", "split_counts", "split_strategy",
                                                  "roboflow_aug_copies", "background_by_class",
                                                  "excluded_non_calamansi")} if dataset else None,
        "leaf_check": {k: gate.get(k) for k in ("generated_at", "calamansi_test_acceptance",
                                                  "negative_test_rejection", "unseen_experiment")} if gate else None,
        "loaded": state["predictor"] is not None,
    }


@app.get("/api/images/{path:path}")
def local_image(path: str, user: CurrentUser = Depends(current_user)):
    """Serves retained images in local-fallback mode (Supabase mode uses signed URLs)."""
    store = repo()
    if not isinstance(store, LocalRepository):
        raise HTTPException(404, "Not found.")
    if not user.is_admin and store.image_owner(path) != user.id:
        raise HTTPException(404, "Image not found.")
    target = (store.images / path).resolve()
    if store.images.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "Image not found.")
    return FileResponse(target, media_type="image/jpeg")


FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Serves the built React app (frontend/dist) so one server runs everything.

    Declared last so every /api route above takes precedence. Unknown paths
    return index.html, letting the React router handle /logs, /reports, etc.
    """
    if path.startswith("api/"):
        raise HTTPException(404, "Not found.")
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        raise HTTPException(404, "Frontend not built. Run `npm run build` in the frontend folder, "
                                 "or use `npm run dev` and open http://localhost:5173.")
    target = (FRONTEND_DIST / path).resolve()
    if path and FRONTEND_DIST.resolve() in target.parents and target.is_file():
        # Built JS/CSS have content hashes in their names, so they can be cached forever.
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        return FileResponse(target, headers={"Cache-Control": cache})
    if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
        # A missing file must 404. Answering with index.html would make the browser
        # run HTML as JavaScript and show a blank page (e.g. after a rebuild).
        raise HTTPException(404, "Not found.")
    # index.html is always revalidated, so a rebuild is picked up on a normal refresh.
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def _reencode_jpeg(data: bytes, max_side: int = 1280) -> bytes:
    """Store a normalised copy: EXIF-rotated, RGB, capped size, metadata (e.g. GPS) stripped."""
    from PIL import ImageOps

    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        return out.getvalue()
