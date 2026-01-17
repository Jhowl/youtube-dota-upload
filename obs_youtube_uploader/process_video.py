from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from pathlib import Path

from zoneinfo import ZoneInfo

from .config import Config
from .description import build_match_description
from .notify import send_finished_notification
from .opendota import (
    fetch_heroes,
    fetch_items,
    fetch_match,
    fetch_player_matches,
    fetch_recent_matches,
    pick_match_for_recording_time,
)
from .youtube_uploader import upload_to_youtube


_FILENAME_RE = re.compile(
    r"(?P<y>\d{4})[-_](?P<mo>\d{2})[-_](?P<d>\d{2})[ _-](?P<h>\d{2})[-_](?P<mi>\d{2})[-_](?P<s>\d{2})"
)


def _parse_obs_filename_time_to_utc(path: Path, tz_name: str) -> datetime:
    base = path.stem
    m = _FILENAME_RE.search(base)
    if not m:
        raise RuntimeError(f"Could not parse datetime from filename: {base}")

    year = int(m.group("y"))
    month = int(m.group("mo"))
    day = int(m.group("d"))
    hour = int(m.group("h"))
    minute = int(m.group("mi"))
    second = int(m.group("s"))

    tz = ZoneInfo(tz_name)
    local_dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def _resolve_match_id(config: Config, recording_start_utc: datetime) -> int:
    recording_epoch = int(recording_start_utc.timestamp())

    window = {
        "before_start_sec": config.match_time_before_sec,
        "after_end_sec": config.match_time_after_sec,
    }

    recent = fetch_recent_matches(config.opendota_player_id)
    match_id = pick_match_for_recording_time(recent, recording_epoch, **window)
    if match_id:
        return match_id

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    days_back = int((now_epoch - recording_epoch) / (24 * 60 * 60)) + 2
    days_back = max(1, min(days_back, 3650))

    older = fetch_player_matches(config.opendota_player_id, limit=200, date_days=days_back)
    match_id = pick_match_for_recording_time(older, recording_epoch, **window)
    if match_id:
        return match_id

    raise RuntimeError(
        f"No match found near recording time ({recording_start_utc.isoformat()}Z). "
        f"Window start-{config.match_time_before_sec}s/end+{config.match_time_after_sec}s. "
        f"Tried recentMatches and players/matches?date={days_back}."
    )


def _description_path(video_path: Path) -> Path:
    return video_path.with_suffix(".txt")


def process_video(config: Config, video_path: Path) -> None:
    started_at = datetime.now(timezone.utc)

    match_id: int | None = None
    youtube_video_id: str | None = None
    description_path: Path | None = None

    try:
        recording_start_utc = _parse_obs_filename_time_to_utc(video_path, config.recording_tz)
        match_id = _resolve_match_id(config, recording_start_utc)

        match = fetch_match(match_id)
        heroes = fetch_heroes()
        items = fetch_items()

        description = build_match_description(
            recording_start_utc=recording_start_utc,
            player_account_id=config.opendota_player_id,
            match=match,
            heroes=heroes,
            items=items,
        )

        description_path = _description_path(video_path)
        description_path.write_text(description, encoding="utf-8")

        title = f"Dota 2 {recording_start_utc.isoformat(timespec='seconds')}Z - Match {match_id}"

        if not config.dry_run:
            print(f"[upload:start] {video_path.name} -> YouTube")
            youtube_video_id = upload_to_youtube(
                config,
                file_path=str(video_path),
                title=title,
                description=description,
            )
            print(f"[upload:done] videoId={youtube_video_id}")

        try:
            send_finished_notification(
                config,
                status="success",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                video_path=str(video_path),
                description_path=str(description_path) if description_path else None,
                match_id=match_id,
                youtube_video_id=youtube_video_id,
            )
        except Exception as notify_err:
            print(f"[notify:error] {notify_err}")

        print(f"[done] {video_path}")

    except Exception as err:
        try:
            send_finished_notification(
                config,
                status="error",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                video_path=str(video_path),
                description_path=str(description_path) if description_path else None,
                match_id=match_id,
                youtube_video_id=youtube_video_id,
                error=str(err),
            )
        except Exception as notify_err:
            print(f"[notify:error] {notify_err}")

        print(f"[process:error] {video_path} {err}")
