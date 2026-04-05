from __future__ import annotations

import asyncio
import queue
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config
from .event_bus import EVENT_BUS
from .process_video import apply_sequence_to_title
from .store import UploadRecord, clear_active_youtube_account, consume_oauth_state, get_active_youtube_account, get_upload
from .uploads import list_records, skip_upload, start_upload, update_record
from .youtube_auth import (
    YouTubeAuthError,
    YouTubeOAuthConfigError,
    begin_youtube_oauth,
    build_credentials,
    fetch_youtube_profile,
    refresh_and_capture_status,
)


class UpdatePayload(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: str | None = None
    sequence: int | None = None


class OAuthStartPayload(BaseModel):
    redirect_path: str | None = "/"


def _record_to_dict(record: UploadRecord) -> dict[str, Any]:
    filename = Path(record.video_path).name
    youtube_url = f"https://www.youtube.com/watch?v={record.youtube_video_id}" if record.youtube_video_id else None
    return {
        "id": record.id,
        "video_path": record.video_path,
        "filename": filename,
        "status": record.status,
        "sequence": record.sequence,
        "title": record.edited_title or record.default_title or "",
        "description": record.edited_description or record.default_description or "",
        "tags": record.edited_tags or record.default_tags or "",
        "default_title": record.default_title or "",
        "default_description": record.default_description or "",
        "default_tags": record.default_tags or "",
        "thumbnail_prompt": record.thumbnail_prompt or "",
        "description_path": record.description_path,
        "match_id": record.match_id,
        "youtube_video_id": record.youtube_video_id,
        "youtube_url": youtube_url,
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _build_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _youtube_status(config: Config) -> dict[str, Any]:
    active = get_active_youtube_account(config.uploads_db_path)
    fallback_ready = bool(config.youtube_client_id and config.youtube_client_secret and config.youtube_refresh_token)

    if active:
        return {
            "connected": True,
            "source": "db",
            "channel_title": active.channel_title,
            "channel_id": active.channel_id,
            "google_account_email": active.google_account_email,
            "token_status": "ok" if not active.last_error else "error",
            "last_refreshed_at": active.last_refreshed_at,
            "error": active.last_error or None,
            "has_env_fallback": fallback_ready,
        }

    if fallback_ready:
        return {
            "connected": True,
            "source": "env",
            "channel_title": None,
            "channel_id": None,
            "google_account_email": None,
            "token_status": "fallback",
            "last_refreshed_at": None,
            "error": None,
            "has_env_fallback": True,
        }

    return {
        "connected": False,
        "source": None,
        "channel_title": None,
        "channel_id": None,
        "google_account_email": None,
        "token_status": "missing",
        "last_refreshed_at": None,
        "error": None,
        "has_env_fallback": False,
    }


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="OBS YouTube Uploader")
    app.state.config = config

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html_path = static_dir / "index.html"
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/api/videos")
    def list_videos() -> dict[str, Any]:
        records = list_records(config)
        return {"items": [_record_to_dict(r) for r in records]}

    @app.patch("/api/videos/{upload_id}")
    def update_video(upload_id: int, payload: UpdatePayload) -> dict[str, Any]:
        record = get_upload(config.uploads_db_path, upload_id)
        if not record:
            raise HTTPException(status_code=404, detail="Upload not found")

        fields: dict[str, Any] = {}
        if payload.title is not None:
            fields["edited_title"] = payload.title
        if payload.description is not None:
            fields["edited_description"] = payload.description
        if payload.tags is not None:
            fields["edited_tags"] = payload.tags
        if payload.sequence is not None:
            fields["sequence"] = payload.sequence

        if payload.sequence is not None:
            base_title = fields.get("edited_title") or record.edited_title or record.default_title or ""
            fields["edited_title"] = apply_sequence_to_title(base_title, payload.sequence)

        updated = update_record(config, upload_id, fields)
        if not updated:
            raise HTTPException(status_code=404, detail="Upload not found")

        return _record_to_dict(updated)

    @app.post("/api/videos/{upload_id}/upload")
    def upload_video(upload_id: int) -> dict[str, Any]:
        started = start_upload(config, upload_id)
        if not started:
            raise HTTPException(status_code=400, detail="Upload already running or invalid state")
        return {"ok": True}

    @app.post("/api/videos/{upload_id}/skip")
    def skip_video(upload_id: int) -> dict[str, Any]:
        record = skip_upload(config, upload_id)
        if not record:
            raise HTTPException(status_code=404, detail="Upload not found")
        return _record_to_dict(record)

    @app.get("/api/youtube/status")
    def youtube_status() -> dict[str, Any]:
        return _youtube_status(config)

    @app.post("/api/youtube/connect/start")
    def youtube_connect_start(payload: OAuthStartPayload, request: Request) -> dict[str, Any]:
        try:
            auth_url = begin_youtube_oauth(config, _build_base_url(request), payload.redirect_path)
        except YouTubeOAuthConfigError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {"auth_url": auth_url}

    @app.get("/api/youtube/connect/callback")
    def youtube_connect_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
        redirect_target = "/"
        if state:
            consumed = consume_oauth_state(config.uploads_db_path, state, "youtube")
            if consumed and consumed.redirect_path:
                redirect_target = consumed.redirect_path
            elif not consumed:
                redirect_target = "/?youtube=error&message=Invalid+or+expired+state"
                return RedirectResponse(redirect_target, status_code=303)

        if error:
            q = urlencode({"youtube": "error", "message": error})
            return RedirectResponse(f"{redirect_target}?{q}" if "?" not in redirect_target else f"{redirect_target}&{q}", status_code=303)
        if not code:
            q = urlencode({"youtube": "error", "message": "Missing authorization code"})
            return RedirectResponse(f"{redirect_target}?{q}" if "?" not in redirect_target else f"{redirect_target}&{q}", status_code=303)

        try:
            from .youtube_auth import finish_youtube_oauth

            finish_youtube_oauth(config, base_url=_build_base_url(request), code=code)
            q = urlencode({"youtube": "connected"})
        except Exception as err:
            q = urlencode({"youtube": "error", "message": str(err)})

        return RedirectResponse(f"{redirect_target}?{q}" if "?" not in redirect_target else f"{redirect_target}&{q}", status_code=303)

    @app.post("/api/youtube/disconnect")
    def youtube_disconnect() -> dict[str, Any]:
        clear_active_youtube_account(config.uploads_db_path)
        return {"ok": True}

    @app.post("/api/youtube/refresh-test")
    def youtube_refresh_test() -> dict[str, Any]:
        try:
            resolved, creds = build_credentials(config)
            refresh_and_capture_status(config, creds, resolved)
            profile = fetch_youtube_profile(creds)
            return {
                "ok": True,
                "source": resolved.source,
                "channel_id": profile.channel_id,
                "channel_title": profile.channel_title,
                "google_account_email": profile.google_account_email,
            }
        except YouTubeAuthError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err)) from err

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        async def event_stream():
            q = EVENT_BUS.subscribe()
            try:
                while True:
                    try:
                        event = await asyncio.to_thread(q.get, True, 15)
                        payload = event.to_json()
                        yield f"data: {payload}\n\n"
                    except queue.Empty:
                        yield "event: ping\ndata: {}\n\n"
            finally:
                EVENT_BUS.unsubscribe(q)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app
