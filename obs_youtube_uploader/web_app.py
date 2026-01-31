from __future__ import annotations

import asyncio
import queue
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config
from .event_bus import EVENT_BUS
from .process_video import apply_sequence_to_title
from .store import UploadRecord, get_upload
from .uploads import list_records, skip_upload, start_upload, update_record


class UpdatePayload(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: str | None = None
    sequence: int | None = None


def _record_to_dict(record: UploadRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "video_path": record.video_path,
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
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
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
