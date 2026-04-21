from __future__ import annotations

from typing import Any

import re

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config
from .youtube_auth import build_credentials, fetch_youtube_profile, refresh_and_capture_status
from .store import update_youtube_account_status


def _sanitize_description(description: str) -> str:
    text = description.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\x00', '')
    text = re.sub(r'[\u2028\u2029]', '\n', text)
    text = ''.join(ch for ch in text if ch == '\n' or ch == '\t' or ord(ch) >= 32)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:4900]


def _ascii_fallback_description(description: str) -> str:
    text = _sanitize_description(description)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\x09\x0A\x20-\x7E]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:3500]


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

    safe_description = _sanitize_description(description)

    body: dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": safe_description,
            "categoryId": config.youtube_category_id,
            "tags": tags if tags is not None else (config.youtube_tags or None),
        },
        "status": {"privacyStatus": config.youtube_privacy_status},
    }

    print(f"[upload] uploading file: {file_path}")

    def _run_insert(insert_body: dict[str, Any]) -> str:
        request = youtube.videos().insert(
            part="snippet,status",
            body=insert_body,
            media_body=MediaFileUpload(file_path, resumable=True),
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response.get("id") if isinstance(response, dict) else None
        if not video_id:
            raise RuntimeError("YouTube upload did not return a video id")
        return str(video_id)

    try:
        return _run_insert(body)
    except Exception as err:
        if 'invalidDescription' not in str(err):
            raise
        fallback_body = {
            **body,
            'snippet': {
                **body['snippet'],
                'description': _ascii_fallback_description(description),
            },
        }
        return _run_insert(fallback_body)
