from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _run_headless(flow: InstalledAppFlow) -> object:
    """Headless OAuth helper.

    Some versions of google-auth-oauthlib don't have `run_console`, so we implement
    the console flow manually.
    """
    # Note: redirect_uri must match one allowed for InstalledAppFlow.
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print("\nOpen this URL in a browser and authorize the app:")
    print(auth_url)
    print("\nThen paste the authorization code here:")
    code = input("Code: ").strip()
    if not code:
        raise RuntimeError("No code provided")

    flow.fetch_token(code=code)
    return flow.credentials


def main() -> None:
    load_dotenv()

    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    client_secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE")

    if client_secrets_file:
        client_secrets_path = Path(client_secrets_file)
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
    else:
        if not client_id or not client_secret:
            raise RuntimeError(
                "Set YOUTUBE_CLIENT_SECRETS_FILE (recommended) or set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET"
            )
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    # Headless-friendly OAuth flow:
    creds = _run_headless(flow)

    refresh_token = getattr(creds, "refresh_token", None)
    if not refresh_token:
        raise RuntimeError(
            "No refresh_token returned. Revoke the app in your Google Account and run again."
        )

    print("\nYOUTUBE_REFRESH_TOKEN=")
    print(refresh_token)


if __name__ == "__main__":
    main()
