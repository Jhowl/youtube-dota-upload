from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    watch_folder: Path
    video_extensions: set[str]
    process_existing: bool
    dry_run: bool

    recording_tz: str
    match_time_before_sec: int
    match_time_after_sec: int

    opendota_player_id: int
    n8n_webhook_url: str

    youtube_client_id: str
    youtube_client_secret: str
    youtube_refresh_token: str
    youtube_privacy_status: str
    youtube_category_id: str | None
    youtube_tags: list[str]


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_extensions(value: str | None) -> set[str]:
    raw = value or ".mp4,.mkv"
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip().lower()
        if not p:
            continue
        if not p.startswith("."):
            p = f".{p}"
        out.add(p)
    return out


def load_config() -> Config:
    load_dotenv()

    dry_run = _parse_bool(os.getenv("DRY_RUN"), False)

    watch_folder = Path(os.getenv("WATCH_FOLDER") or (Path.cwd() / "watch")).resolve()

    recording_tz = os.getenv("RECORDING_TZ") or "America/New_York"

    match_time_before_sec = int(os.getenv("MATCH_TIME_BEFORE_SEC") or str(3 * 60 * 60))
    match_time_after_sec = int(os.getenv("MATCH_TIME_AFTER_SEC") or str(3 * 60 * 60))

    opendota_player_id = int(os.getenv("OPENDOTA_PLAYER_ID") or "115732760")

    n8n_webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if not n8n_webhook_url:
        raise RuntimeError("Missing N8N_WEBHOOK_URL")

    youtube_client_id = os.getenv("YOUTUBE_CLIENT_ID") or ""
    youtube_client_secret = os.getenv("YOUTUBE_CLIENT_SECRET") or ""
    youtube_refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN") or ""

    youtube_privacy_status = os.getenv("YOUTUBE_PRIVACY_STATUS") or "unlisted"
    youtube_category_id = os.getenv("YOUTUBE_CATEGORY_ID") or None
    youtube_tags = [t.strip() for t in (os.getenv("YOUTUBE_TAGS") or "").split(",") if t.strip()]

    if not dry_run:
        if not youtube_client_id:
            raise RuntimeError("Missing YOUTUBE_CLIENT_ID (or set DRY_RUN=true)")
        if not youtube_client_secret:
            raise RuntimeError("Missing YOUTUBE_CLIENT_SECRET (or set DRY_RUN=true)")
        if not youtube_refresh_token:
            raise RuntimeError("Missing YOUTUBE_REFRESH_TOKEN (or set DRY_RUN=true)")

    return Config(
        watch_folder=watch_folder,
        video_extensions=_parse_extensions(os.getenv("VIDEO_EXTENSIONS")),
        process_existing=_parse_bool(os.getenv("PROCESS_EXISTING"), False),
        dry_run=dry_run,
        recording_tz=recording_tz,
        match_time_before_sec=match_time_before_sec,
        match_time_after_sec=match_time_after_sec,
        opendota_player_id=opendota_player_id,
        n8n_webhook_url=n8n_webhook_url,
        youtube_client_id=youtube_client_id,
        youtube_client_secret=youtube_client_secret,
        youtube_refresh_token=youtube_refresh_token,
        youtube_privacy_status=youtube_privacy_status,
        youtube_category_id=youtube_category_id,
        youtube_tags=youtube_tags,
    )
