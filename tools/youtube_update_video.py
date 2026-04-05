"""Update title/description/tags for an existing YouTube video.

Usage:
  python tools/youtube_update_video.py --video-id <id> --title "..." --description "..." [--tags "a,b,c"]

Requires env vars (same as uploader):
  YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

Note: The refresh token must include scopes that permit videos.update.
"""

from __future__ import annotations

import argparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--video-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--tags", default="")
    args = p.parse_args()

    # Import config lazily so it reads env the same way as the app.
    from obs_youtube_uploader.config import load_config  # type: ignore

    config = load_config()

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    # Use a broader scope than upload; may still fail if refresh token doesn't include it.
    scopes = [
        "https://www.googleapis.com/auth/youtube",
    ]

    creds = Credentials(
        token=None,
        refresh_token=config.youtube_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.youtube_client_id,
        client_secret=config.youtube_client_secret,
        scopes=scopes,
    )

    print("[youtube:update] refreshing access token")
    creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "id": args.video_id,
        "snippet": {
            "title": args.title,
            "description": args.description,
            "categoryId": config.youtube_category_id,
            "tags": tags or (config.youtube_tags or None),
        },
    }

    print(f"[youtube:update] updating videoId={args.video_id}")
    resp = youtube.videos().update(part="snippet", body=body).execute()
    print("[youtube:update] ok")
    print(resp)


if __name__ == "__main__":
    main()
