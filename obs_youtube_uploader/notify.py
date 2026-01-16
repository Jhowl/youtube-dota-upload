from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from .config import Config


def send_finished_notification(
    config: Config,
    *,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    video_path: str,
    description_path: str | None,
    match_id: int | None,
    youtube_video_id: str | None,
    error: str | None = None,
) -> None:
    if config.dry_run:
        return

    payload: dict[str, Any] = {
        "status": status,
        "startedAt": started_at.isoformat() + "Z",
        "finishedAt": finished_at.isoformat() + "Z",
        "videoPath": video_path,
        "descriptionPath": description_path,
        "matchId": match_id,
        "youtubeVideoId": youtube_video_id,
        "error": error,
    }

    res = requests.post(config.n8n_webhook_url, json=payload, timeout=30)
    res.raise_for_status()
