from __future__ import annotations

import os

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


def main() -> None:
    load_dotenv()

    client_id = (os.getenv("YOUTUBE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("YOUTUBE_CLIENT_SECRET") or "").strip()
    refresh_token = (os.getenv("YOUTUBE_REFRESH_TOKEN") or "").strip()

    if not client_id or not client_secret or not refresh_token:
        raise SystemExit("Missing YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    creds.refresh(Request())

    print("OK: refreshed access token")


if __name__ == "__main__":
    main()
