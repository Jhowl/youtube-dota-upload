from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
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


@dataclass(frozen=True)
class YouTubeAccountRecord:
    id: int
    provider: str
    google_account_email: str | None
    channel_id: str | None
    channel_title: str | None
    client_id: str
    client_secret: str
    refresh_token: str
    scope: str | None
    token_uri: str
    active: int
    last_refreshed_at: str | None
    last_error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class OAuthStateRecord:
    id: int
    state: str
    provider: str
    redirect_path: str | None
    created_at: str
    expires_at: str


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                google_account_email TEXT,
                channel_id TEXT,
                channel_title TEXT,
                client_id TEXT NOT NULL,
                client_secret TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                scope TEXT,
                token_uri TEXT NOT NULL DEFAULT 'https://oauth2.googleapis.com/token',
                active INTEGER NOT NULL DEFAULT 1,
                last_refreshed_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_youtube_accounts_active ON youtube_accounts(active)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                redirect_path TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oauth_states_expires_at ON oauth_states(expires_at)")
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


def _row_to_youtube_account(row: sqlite3.Row | None) -> YouTubeAccountRecord | None:
    if not row:
        return None
    return YouTubeAccountRecord(**dict(row))


def _row_to_oauth_state(row: sqlite3.Row | None) -> OAuthStateRecord | None:
    if not row:
        return None
    return OAuthStateRecord(**dict(row))


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


def get_active_youtube_account(db_path: Path) -> YouTubeAccountRecord | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM youtube_accounts WHERE provider = 'youtube' AND active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _row_to_youtube_account(row)


def upsert_youtube_account(
    db_path: Path,
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    scope: str | None,
    token_uri: str,
    google_account_email: str | None,
    channel_id: str | None,
    channel_title: str | None,
    last_refreshed_at: str | None = None,
    last_error: str | None = None,
) -> YouTubeAccountRecord:
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute("UPDATE youtube_accounts SET active = 0, updated_at = ? WHERE provider = 'youtube'", (now,))
        existing = conn.execute(
            "SELECT * FROM youtube_accounts WHERE provider = 'youtube' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE youtube_accounts
                SET google_account_email = ?, channel_id = ?, channel_title = ?, client_id = ?, client_secret = ?,
                    refresh_token = ?, scope = ?, token_uri = ?, active = 1, last_refreshed_at = ?,
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    google_account_email,
                    channel_id,
                    channel_title,
                    client_id,
                    client_secret,
                    refresh_token,
                    scope,
                    token_uri,
                    last_refreshed_at,
                    last_error,
                    now,
                    existing["id"],
                ),
            )
            row = conn.execute("SELECT * FROM youtube_accounts WHERE id = ?", (existing["id"],)).fetchone()
        else:
            conn.execute(
                """
                INSERT INTO youtube_accounts (
                    provider, google_account_email, channel_id, channel_title, client_id, client_secret,
                    refresh_token, scope, token_uri, active, last_refreshed_at, last_error, created_at, updated_at
                ) VALUES ('youtube', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    google_account_email,
                    channel_id,
                    channel_title,
                    client_id,
                    client_secret,
                    refresh_token,
                    scope,
                    token_uri,
                    last_refreshed_at,
                    last_error,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM youtube_accounts WHERE provider = 'youtube' AND active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
    account = _row_to_youtube_account(row)
    if not account:
        raise RuntimeError("Failed to store YouTube account")
    return account


def clear_active_youtube_account(db_path: Path) -> None:
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE youtube_accounts SET active = 0, updated_at = ? WHERE provider = 'youtube' AND active = 1",
            (now,),
        )


def update_youtube_account_status(
    db_path: Path,
    account_id: int,
    *,
    last_refreshed_at: str | None = None,
    last_error: str | None = None,
    channel_id: str | None = None,
    channel_title: str | None = None,
    google_account_email: str | None = None,
) -> YouTubeAccountRecord | None:
    fields: dict[str, Any] = {}
    if last_refreshed_at is not None:
        fields["last_refreshed_at"] = last_refreshed_at
    if last_error is not None:
        fields["last_error"] = last_error
    if channel_id is not None:
        fields["channel_id"] = channel_id
    if channel_title is not None:
        fields["channel_title"] = channel_title
    if google_account_email is not None:
        fields["google_account_email"] = google_account_email
    if not fields:
        with _connect(db_path) as conn:
            row = conn.execute("SELECT * FROM youtube_accounts WHERE id = ?", (account_id,)).fetchone()
        return _row_to_youtube_account(row)

    fields["updated_at"] = _utc_now()
    sets = ", ".join([f"{k} = ?" for k in fields.keys()])
    values = list(fields.values()) + [account_id]
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE youtube_accounts SET {sets} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM youtube_accounts WHERE id = ?", (account_id,)).fetchone()
    return _row_to_youtube_account(row)


def cleanup_expired_oauth_states(db_path: Path) -> None:
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now,))


def create_oauth_state(db_path: Path, provider: str, redirect_path: str | None = None, ttl_minutes: int = 15) -> OAuthStateRecord:
    cleanup_expired_oauth_states(db_path)
    state = secrets.token_urlsafe(32)
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat().replace("+00:00", "Z")
    expires_at = (now_dt + timedelta(minutes=ttl_minutes)).isoformat().replace("+00:00", "Z")
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO oauth_states (state, provider, redirect_path, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (state, provider, redirect_path, now, expires_at),
        )
        row = conn.execute("SELECT * FROM oauth_states WHERE state = ?", (state,)).fetchone()
    rec = _row_to_oauth_state(row)
    if not rec:
        raise RuntimeError("Failed to create oauth state")
    return rec


def consume_oauth_state(db_path: Path, state: str, provider: str) -> OAuthStateRecord | None:
    cleanup_expired_oauth_states(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_states WHERE state = ? AND provider = ?",
            (state, provider),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM oauth_states WHERE id = ?", (row["id"],))
    return _row_to_oauth_state(row)
