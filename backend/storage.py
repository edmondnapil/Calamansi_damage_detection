"""Persistence for detection records and retained leaf images.

Two interchangeable backends:

* SupabaseRepository - PostgreSQL table `detection_logs` + private Storage
  bucket. Used whenever SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.
* LocalRepository    - SQLite file + local folder in backend/data/. A fallback
  so the app can be tried before Supabase is configured. It is reported as
  "local" in /api/health and the Settings page; it is not the production store.

Only the backend talks to the database. The service-role key never leaves
this process, and records are created exclusively from the model's output.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config import BACKEND_DIR, CLASS_NAMES

log = logging.getLogger("calamansi.storage")
APP_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Manila"))
BUCKET = os.getenv("SUPABASE_BUCKET", "leaf-images")
SIGNED_URL_SECONDS = 3600


def local_day_bounds(date_from: date | None, date_to: date | None) -> tuple[str | None, str | None]:
    """Convert inclusive local calendar dates to UTC ISO timestamps [start, end)."""
    start = datetime.combine(date_from, datetime.min.time(), APP_TZ).astimezone(timezone.utc).isoformat() \
        if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), APP_TZ).astimezone(timezone.utc).isoformat() \
        if date_to else None
    return start, end


def daily_series(rows: list[dict], date_from: date, date_to: date) -> list[dict]:
    """Bucket (created_at, predicted_class) rows into one entry per local day, zero-filled."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {c: 0 for c in CLASS_NAMES})
    for r in rows:
        ts = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
        counts[ts.astimezone(APP_TZ).date().isoformat()][r["predicted_class"]] += 1
    out, d = [], date_from
    while d <= date_to:
        out.append({"date": d.isoformat(), **counts.get(d.isoformat(), {c: 0 for c in CLASS_NAMES})})
        d += timedelta(days=1)
    return out


class Repository(ABC):
    backend = "none"

    @abstractmethod
    def status(self) -> dict: ...

    @abstractmethod
    def save_image(self, data: bytes, created: datetime) -> str: ...

    @abstractmethod
    def insert(self, record: dict) -> dict: ...

    @abstractmethod
    def get(self, detection_id: str) -> dict | None: ...

    # `owner`: the user id whose records to use; None = all users (administrators only).
    @abstractmethod
    def list(self, *, search: str | None, predicted_class: str | None, date_from: date | None,
             date_to: date | None, offset: int, limit: int, owner: str | None) -> tuple[list[dict], int]: ...

    @abstractmethod
    def count(self, predicted_class: str | None = None, date_from: date | None = None,
              date_to: date | None = None, *, owner: str | None) -> int: ...

    @abstractmethod
    def rows_between(self, date_from: date, date_to: date, *, owner: str | None) -> list[dict]:
        """Minimal rows (created_at, predicted_class, confidence) for charts/reports."""

    @abstractmethod
    def image_urls(self, paths: list[str]) -> dict[str, str]: ...

    @abstractmethod
    def delete_owner_records(self, owner: str) -> int:
        """Delete all detections (and stored images) of one user; returns the number of detections."""

    def with_image_urls(self, items: list[dict]) -> list[dict]:
        urls = self.image_urls([i["image_path"] for i in items if i.get("image_path")])
        for i in items:
            i["image_url"] = urls.get(i.get("image_path") or "")
        return items


# --------------------------------------------------------------------------- Supabase
class SupabaseRepository(Repository):
    backend = "supabase"
    TABLE = "detection_logs"

    RETRIES = 3

    def __init__(self, url: str, service_key: str):
        import httpx
        from supabase import ClientOptions, create_client

        # FastAPI runs these calls from several worker threads at once (the dashboard
        # alone fires 3-4 requests in parallel). The default client multiplexes them
        # over one shared HTTP/2 connection, which intermittently fails with
        # "RemoteProtocolError: Server disconnected". A plain HTTP/1.1 pool gives each
        # concurrent call its own connection; idle connections are dropped before
        # Supabase's load balancer closes them.
        http = httpx.Client(http2=False, timeout=httpx.Timeout(30.0, connect=10.0),
                            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10,
                                                keepalive_expiry=20.0))
        self.client = create_client(url, service_key, ClientOptions(httpx_client=http))
        self.url = url

    def _t(self):
        return self.client.table(self.TABLE)

    def _run(self, call):
        """Run a Supabase call, retrying when the network connection drops.

        Only transport-level failures are retried; API errors such as a missing table
        are raised immediately. Pass a fully built query's bound `.execute` (the
        builders mutate themselves, so the query must not be rebuilt per attempt);
        every call passed here is safe to repeat.
        """
        import httpx

        for attempt in range(self.RETRIES):
            try:
                return call()
            except httpx.TransportError as e:
                if attempt == self.RETRIES - 1:
                    raise
                log.warning("Supabase connection error (%s), retrying", type(e).__name__)
                time.sleep(0.2 * (attempt + 1))

    def status(self) -> dict:
        try:
            self._run(self._t().select("id", count="exact").limit(1).execute)
            return {"backend": self.backend, "connected": True, "bucket": BUCKET}
        except Exception as e:  # report, never raise: used by /api/health
            return {"backend": self.backend, "connected": False, "bucket": BUCKET, "error": _safe_error(e)}

    def save_image(self, data: bytes, created: datetime) -> str:
        path = f"{created:%Y/%m}/{uuid.uuid4()}.jpg"
        # upsert makes a retry after a dropped connection harmless (same unique path).
        self._run(lambda: self.client.storage.from_(BUCKET).upload(
            path, data, {"content-type": "image/jpeg", "upsert": "true"}))
        return path

    def insert(self, record: dict) -> dict:
        # The id is generated here so a retried request upserts the same row
        # instead of creating a duplicate.
        record = {**record, "id": str(uuid.uuid4())}
        return self._run(self._t().upsert(record, on_conflict="id").execute).data[0]

    def get(self, detection_id: str) -> dict | None:
        rows = self._run(self._t().select("*").eq("id", detection_id).limit(1).execute).data
        return rows[0] if rows else None

    def _filtered(self, q, predicted_class, date_from, date_to, search=None, owner=None):
        start, end = local_day_bounds(date_from, date_to)
        if owner is not None:
            q = q.eq("user_id", owner)
        if predicted_class:
            q = q.eq("predicted_class", predicted_class)
        if start:
            q = q.gte("created_at", start)
        if end:
            q = q.lt("created_at", end)
        if search:
            term = search.replace(",", " ").replace("(", " ").replace(")", " ").strip()
            if term:
                q = q.or_(f"original_filename.ilike.*{term}*,predicted_class.ilike.*{term}*,model_version.ilike.*{term}*")
        return q

    def list(self, *, search, predicted_class, date_from, date_to, offset, limit, owner):
        q = self._filtered(self._t().select("*", count="exact"), predicted_class, date_from, date_to, search, owner)
        res = self._run(q.order("created_at", desc=True).range(offset, offset + limit - 1).execute)
        return res.data, res.count or 0

    def count(self, predicted_class=None, date_from=None, date_to=None, *, owner) -> int:
        q = self._filtered(self._t().select("id", count="exact"), predicted_class, date_from, date_to, owner=owner)
        return self._run(q.limit(1).execute).count or 0

    def rows_between(self, date_from, date_to, *, owner):
        rows, page = [], 1000
        while True:  # PostgREST caps responses, so page through
            q = self._filtered(self._t().select("created_at,predicted_class,confidence"), None, date_from, date_to,
                               owner=owner)
            batch = self._run(q.order("created_at").range(len(rows), len(rows) + page - 1).execute).data
            rows.extend(batch)
            if len(batch) < page:
                return rows

    def delete_owner_records(self, owner: str) -> int:
        rows, offset = [], 0
        while True:
            batch = self._run(self._t().select("id,image_path").eq("user_id", owner).range(offset, offset + 999).execute).data
            rows += batch
            offset += 1000
            if len(batch) < 1000:
                break
        paths = [r["image_path"] for r in rows if r.get("image_path")]
        for i in range(0, len(paths), 100):
            self._run(lambda chunk=paths[i:i + 100]: self.client.storage.from_(BUCKET).remove(chunk))
        if rows:
            self._run(self._t().delete().eq("user_id", owner).execute)
        return len(rows)

    def image_urls(self, paths):
        if not paths:
            return {}
        try:
            signed = self._run(lambda: self.client.storage.from_(BUCKET).create_signed_urls(paths, SIGNED_URL_SECONDS))
            return {s["path"]: s.get("signedURL") or s.get("signedUrl") for s in signed if not s.get("error")}
        except Exception:
            return {}


# --------------------------------------------------------------------------- Local fallback
class LocalRepository(Repository):
    backend = "local"

    def __init__(self, folder: Path | None = None):
        folder = folder or Path(os.getenv("LOCAL_DATA_DIR", str(BACKEND_DIR / "data")))
        self.folder = folder
        self.images = folder / "uploads"
        self.images.mkdir(parents=True, exist_ok=True)
        self.db_path = folder / "local_detections.db"
        self.lock = threading.Lock()
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS detection_logs (
                id TEXT PRIMARY KEY,
                predicted_class TEXT NOT NULL CHECK (predicted_class IN ('Healthy','Damaged')),
                confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                prob_healthy REAL, prob_damaged REAL,
                image_path TEXT, original_filename TEXT,
                model_version TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_created ON detection_logs(created_at DESC)")
            if "user_id" not in {r[1] for r in c.execute("PRAGMA table_info(detection_logs)")}:
                c.execute("ALTER TABLE detection_logs ADD COLUMN user_id TEXT")  # databases created before accounts
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_created ON detection_logs(user_id, created_at DESC)")

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def status(self) -> dict:
        return {"backend": self.backend, "connected": True,
                "note": "Supabase is not configured; records are stored in backend/data/local_detections.db"}

    def save_image(self, data: bytes, created: datetime) -> str:
        rel = f"{created:%Y/%m}/{uuid.uuid4()}.jpg"
        dest = self.images / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return rel

    def insert(self, record: dict) -> dict:
        record = {**record, "id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()}
        cols = ",".join(record)
        with self.lock, self._conn() as c:
            c.execute(f"INSERT INTO detection_logs ({cols}) VALUES ({','.join('?' * len(record))})",
                      list(record.values()))
        return record

    def get(self, detection_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM detection_logs WHERE id = ?", (detection_id,)).fetchone()
        return dict(row) if row else None

    def _where(self, predicted_class, date_from, date_to, search=None, owner=None):
        start, end = local_day_bounds(date_from, date_to)
        clauses, params = [], []
        if owner is not None:
            clauses.append("user_id = ?"); params.append(owner)
        if predicted_class:
            clauses.append("predicted_class = ?"); params.append(predicted_class)
        if start:
            clauses.append("created_at >= ?"); params.append(start)
        if end:
            clauses.append("created_at < ?"); params.append(end)
        if search:
            clauses.append("(original_filename LIKE ? OR predicted_class LIKE ? OR model_version LIKE ?)")
            params += [f"%{search}%"] * 3
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def list(self, *, search, predicted_class, date_from, date_to, offset, limit, owner):
        where, params = self._where(predicted_class, date_from, date_to, search, owner)
        with self._conn() as c:
            total = c.execute(f"SELECT COUNT(*) FROM detection_logs{where}", params).fetchone()[0]
            rows = c.execute(f"SELECT * FROM detection_logs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                             params + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total

    def count(self, predicted_class=None, date_from=None, date_to=None, *, owner) -> int:
        where, params = self._where(predicted_class, date_from, date_to, owner=owner)
        with self._conn() as c:
            return c.execute(f"SELECT COUNT(*) FROM detection_logs{where}", params).fetchone()[0]

    def rows_between(self, date_from, date_to, *, owner):
        where, params = self._where(None, date_from, date_to, owner=owner)
        with self._conn() as c:
            rows = c.execute(f"SELECT created_at, predicted_class, confidence FROM detection_logs{where}",
                             params).fetchall()
        return [dict(r) for r in rows]

    def image_urls(self, paths):
        return {p: f"/api/images/{p}" for p in paths}

    def delete_owner_records(self, owner: str) -> int:
        with self.lock, self._conn() as c:
            rows = c.execute("SELECT image_path FROM detection_logs WHERE user_id = ?", (owner,)).fetchall()
            c.execute("DELETE FROM detection_logs WHERE user_id = ?", (owner,))
        for (path,) in rows:
            if path:
                target = (self.images / path).resolve()
                if self.images.resolve() in target.parents:
                    target.unlink(missing_ok=True)
        return len(rows)

    def image_owner(self, path: str) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT user_id FROM detection_logs WHERE image_path = ? LIMIT 1", (path,)).fetchone()
        return row[0] if row else None


def _safe_error(e: Exception) -> str:
    """Error text without anything that could look like a credential."""
    msg = str(e).splitlines()[0][:200]
    for secret in (os.getenv("SUPABASE_SERVICE_ROLE_KEY"), os.getenv("SUPABASE_KEY")):
        if secret:
            msg = msg.replace(secret, "***")
    return msg


def create_repository() -> Repository:
    mode = os.getenv("DB_BACKEND", "auto").lower()
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if "YOUR-" in url or "YOUR-" in key:  # untouched placeholders from .env.example
        url = key = ""
    if mode == "local" or (mode == "auto" and not (url and key)):
        return LocalRepository()
    if not (url and key):
        raise RuntimeError("DB_BACKEND=supabase but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set")
    return SupabaseRepository(url, key)
