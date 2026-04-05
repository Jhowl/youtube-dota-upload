from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config
from .youtube_auth import build_credentials, fetch_youtube_profile, refresh_and_capture_status
from .store import update_youtube_account_status


def upload_to_youtube(
    config: Config,
    *,
    file_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
) -> str:
    resolved, creds = build_credentials(config)

    print(f"[upload] refreshing access token ({resolved.source})")
    refresh_and_capture_status(config, creds, resolved)

    if resolved.account_id is not None:
        try:
            profile = fetch_youtube_profile(creds)
            update_youtube_account_status(
                config.uploads_db_path,
                resolved.account_id,
                channel_id=profile.channel_id,
                channel_title=profile.channel_title,
                google_account_email=profile.google_account_email,
            )
        except Exception as err:
            update_youtube_account_status(
                config.uploads_db_path,
                resolved.account_id,
                last_error=str(err),
            )

    youtube = build("youtube", "v3", credentials=creds)

    body: dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": config.youtube_category_id,
            "tags": tags if tags is not None else (config.youtube_tags or None),
        },
        "status": {"privacyStatus": config.youtube_privacy_status},
    }

    print(f"[upload] uploading file: {file_path}")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(file_path, resumable=True),
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response.get("id") if isinstance(response, dict) else None
    if not video_id:
        raise RuntimeError("YouTube upload did not return a video id")

    return str(video_id)
