from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True)
class UploadRecord:
    id: int
    video_path: str
    status: str
    default_title: str | None
    default_description: str | None
    default_tags: str | None
    sequence: int | None
    edited_title: str | None
    edited_description: str | None
    edited_tags: str | None
    description_path: str | None
    match_id: int | None
    thumbnail_prompt: str | None
    youtube_video_id: str | None
    error: str | None
    created_at: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                default_title TEXT,
                default_description TEXT,
                default_tags TEXT,
                sequence INTEGER,
                edited_title TEXT,
                edited_description TEXT,
                edited_tags TEXT,
                description_path TEXT,
                match_id INTEGER,
                thumbnail_prompt TEXT,
                youtube_video_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status)")
        _ensure_columns(conn)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(uploads)")}
    if "thumbnail_prompt" not in columns:
        conn.execute("ALTER TABLE uploads ADD COLUMN thumbnail_prompt TEXT")


def get_next_sequence(db_path: Path, sequence_start: int) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT MAX(sequence) AS max_seq FROM uploads").fetchone()
    max_seq = int(row["max_seq"]) if row and row["max_seq"] is not None else None
    if max_seq is None:
        return sequence_start
    return max(max_seq + 1, sequence_start)


def _row_to_record(row: sqlite3.Row | None) -> UploadRecord | None:
    if not row:
        return None
    return UploadRecord(**dict(row))


def get_upload_by_path(db_path: Path, video_path: str) -> UploadRecord | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM uploads WHERE video_path = ?", (video_path,)).fetchone()
    return _row_to_record(row)


def get_upload(db_path: Path, upload_id: int) -> UploadRecord | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    return _row_to_record(row)


def list_uploads(db_path: Path) -> list[UploadRecord]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM uploads ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [UploadRecord(**dict(r)) for r in rows]


def create_upload(
    db_path: Path,
    *,
    video_path: str,
    status: str,
    default_title: str | None,
    default_description: str | None,
    default_tags: str | None,
    sequence: int | None,
    description_path: str | None,
    match_id: int | None,
    thumbnail_prompt: str | None = None,
    error: str | None = None,
) -> UploadRecord:
    now = _utc_now()
    with _connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO uploads (
                    video_path, status, default_title, default_description, default_tags, sequence,
                    edited_title, edited_description, edited_tags, description_path, match_id, thumbnail_prompt,
                    youtube_video_id, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    video_path,
                    status,
                    default_title,
                    default_description,
                    default_tags,
                    sequence,
                    description_path,
                    match_id,
                    thumbnail_prompt,
                    error,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            existing = get_upload_by_path(db_path, video_path)
            if existing:
                return existing
            raise
        row = conn.execute("SELECT * FROM uploads WHERE video_path = ?", (video_path,)).fetchone()
    record = _row_to_record(row)
    if not record:
        raise RuntimeError("Failed to create upload record")
    return record


def update_upload(db_path: Path, upload_id: int, fields: dict[str, Any]) -> UploadRecord | None:
    if not fields:
        return get_upload(db_path, upload_id)

    fields = dict(fields)
    fields["updated_at"] = _utc_now()
    sets = ", ".join([f"{k} = ?" for k in fields.keys()])
    values = list(fields.values()) + [upload_id]

    with _connect(db_path) as conn:
        conn.execute(f"UPDATE uploads SET {sets} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    return _row_to_record(row)


def set_status(
    db_path: Path,
    upload_id: int,
    status: str,
    *,
    error: str | None = None,
    youtube_video_id: str | None = None,
) -> UploadRecord | None:
    fields: dict[str, Any] = {"status": status}
    if error is not None:
        fields["error"] = error
    if youtube_video_id is not None:
        fields["youtube_video_id"] = youtube_video_id
    return update_upload(db_path, upload_id, fields)
