from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

from .config import Config
from .store import (
    YouTubeAccountRecord,
    get_active_youtube_account,
    update_youtube_account_status,
    upsert_youtube_account,
)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
OOB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


@dataclass(frozen=True)
class ResolvedYouTubeCredentials:
    source: str
    client_id: str
    client_secret: str
    refresh_token: str
    scopes: list[str]
    token_uri: str
    account_id: int | None = None
    channel_id: str | None = None
    channel_title: str | None = None
    google_account_email: str | None = None
    last_refreshed_at: str | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class YouTubeProfile:
    channel_id: str | None
    channel_title: str | None
    google_account_email: str | None


class YouTubeAuthError(RuntimeError):
    pass


class YouTubeOAuthConfigError(YouTubeAuthError):
    pass


def _env_scopes() -> list[str]:
    return YOUTUBE_SCOPES


def _oauth_client_values(config: Config) -> tuple[str, str]:
    client_id = (config.youtube_client_id or "").strip()
    client_secret = (config.youtube_client_secret or "").strip()
    if not client_id or not client_secret:
        raise YouTubeOAuthConfigError(
            "Missing YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET in .env"
        )
    return client_id, client_secret


def _installed_client_config(client_id: str, client_secret: str) -> dict[str, Any]:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
        }
    }


def resolve_youtube_credentials(config: Config) -> ResolvedYouTubeCredentials:
    account = get_active_youtube_account(config.uploads_db_path)
    if account and account.refresh_token:
        scopes = [s for s in (account.scope or "").split(" ") if s] or _env_scopes()
        return ResolvedYouTubeCredentials(
            source="db",
            account_id=account.id,
            client_id=account.client_id,
            client_secret=account.client_secret,
            refresh_token=account.refresh_token,
            scopes=scopes,
            token_uri=account.token_uri or TOKEN_URI,
            channel_id=account.channel_id,
            channel_title=account.channel_title,
            google_account_email=account.google_account_email,
            last_refreshed_at=account.last_refreshed_at,
            last_error=account.last_error,
        )

    if config.youtube_client_id and config.youtube_client_secret and config.youtube_refresh_token:
        return ResolvedYouTubeCredentials(
            source="env",
            client_id=config.youtube_client_id,
            client_secret=config.youtube_client_secret,
            refresh_token=config.youtube_refresh_token,
            scopes=_env_scopes(),
            token_uri=TOKEN_URI,
        )

    raise YouTubeAuthError("No YouTube credentials configured")


def build_credentials(config: Config) -> tuple[ResolvedYouTubeCredentials, Credentials]:
    resolved = resolve_youtube_credentials(config)
    creds = Credentials(
        token=None,
        refresh_token=resolved.refresh_token,
        token_uri=resolved.token_uri,
        client_id=resolved.client_id,
        client_secret=resolved.client_secret,
        scopes=resolved.scopes,
    )
    return resolved, creds


def refresh_and_capture_status(config: Config, creds: Credentials, resolved: ResolvedYouTubeCredentials) -> None:
    creds.refresh(Request())
    if resolved.account_id is not None:
        update_youtube_account_status(
            config.uploads_db_path,
            resolved.account_id,
            last_refreshed_at=creds.expiry.isoformat().replace("+00:00", "Z") if creds.expiry else None,
            last_error="",
        )


def fetch_youtube_profile(creds: Credentials) -> YouTubeProfile:
    youtube = build("youtube", "v3", credentials=creds)
    profile_resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = profile_resp.get("items") or []
    channel_id = None
    channel_title = None
    if items:
        first = items[0]
        channel_id = first.get("id")
        snippet = first.get("snippet") or {}
        channel_title = snippet.get("title")

    google_email = None
    try:
        oauth2 = build("oauth2", "v2", credentials=creds)
        userinfo = oauth2.userinfo().get().execute()
        google_email = userinfo.get("email")
    except Exception:
        google_email = None

    return YouTubeProfile(channel_id=channel_id, channel_title=channel_title, google_account_email=google_email)


def begin_legacy_youtube_oauth(config: Config) -> str:
    client_id, client_secret = _oauth_client_values(config)
    flow = InstalledAppFlow.from_client_config(
        _installed_client_config(client_id, client_secret),
        YOUTUBE_SCOPES,
    )
    flow.redirect_uri = OOB_REDIRECT_URI
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    return auth_url


def finish_legacy_youtube_oauth(config: Config, code: str) -> YouTubeAccountRecord:
    client_id, client_secret = _oauth_client_values(config)
    flow = InstalledAppFlow.from_client_config(
        _installed_client_config(client_id, client_secret),
        YOUTUBE_SCOPES,
    )
    flow.redirect_uri = OOB_REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials
    refresh_token = getattr(creds, "refresh_token", None)
    if not refresh_token:
        raise YouTubeAuthError(
            "No refresh token returned. Revoke the app in your Google account and try again."
        )

    profile = fetch_youtube_profile(creds)
    return upsert_youtube_account(
        config.uploads_db_path,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        scope=" ".join(creds.scopes or YOUTUBE_SCOPES),
        token_uri=creds.token_uri or TOKEN_URI,
        google_account_email=profile.google_account_email,
        channel_id=profile.channel_id,
        channel_title=profile.channel_title,
        last_refreshed_at=creds.expiry.isoformat().replace("+00:00", "Z") if creds.expiry else None,
        last_error="",
    )
