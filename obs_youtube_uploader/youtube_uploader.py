from __future__ import annotations

from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config


def upload_to_youtube(
    config: Config,
    *,
    file_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
) -> str:
    creds = Credentials(
        token=None,
        refresh_token=config.youtube_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.youtube_client_id,
        client_secret=config.youtube_client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    print("[upload] refreshing access token")
    creds.refresh(Request())

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
