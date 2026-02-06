from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import threading
from typing import Any

from .config import Config
from .event_bus import EVENT_BUS
from .process_video import build_defaults, perform_upload, apply_sequence_to_title
from .store import (
    UploadRecord,
    create_upload,
    get_next_sequence,
    get_upload,
    list_uploads,
    set_status,
    update_upload,
)


@dataclass(frozen=True)
class UploadPayload:
    title: str
    description: str
    tags: list[str]


def enqueue_video(config: Config, video_path: Path) -> UploadRecord:
    existing = get_upload_by_path_safe(config, str(video_path))
    if existing:
        return existing

    sequence = get_next_sequence(config.uploads_db_path, config.sequence_start)

    try:
        defaults = build_defaults(config, video_path, sequence=sequence)
        record = create_upload(
            config.uploads_db_path,
            video_path=str(video_path),
            status="pending",
            default_title=defaults.title,
            default_description=defaults.description,
            default_tags=",".join(defaults.tags),
            sequence=sequence,
            description_path=str(defaults.description_path),
            match_id=defaults.match_id,
            thumbnail_prompt=defaults.thumbnail_prompt,
        )
    except Exception as err:
        record = create_upload(
            config.uploads_db_path,
            video_path=str(video_path),
            status="error",
            default_title=None,
            default_description=None,
            default_tags=None,
            sequence=sequence,
            description_path=None,
            match_id=None,
            error=str(err),
        )

    EVENT_BUS.publish("upload_created", record_to_event(record))
    return record


def start_upload(config: Config, upload_id: int) -> bool:
    record = get_upload(config.uploads_db_path, upload_id)
    if not record:
        return False
    if record.status in {"uploading", "uploaded", "skipped"}:
        return False

    thread = threading.Thread(
        target=_do_upload,
        args=(config, upload_id),
        daemon=True,
    )
    thread.start()
    return True


def skip_upload(config: Config, upload_id: int) -> UploadRecord | None:
    record = set_status(config.uploads_db_path, upload_id, "skipped")
    if record:
        EVENT_BUS.publish("upload_updated", record_to_event(record))
    return record


def list_records(config: Config) -> list[UploadRecord]:
    return list_uploads(config.uploads_db_path)


def update_record(config: Config, upload_id: int, fields: dict[str, Any]) -> UploadRecord | None:
    record = update_upload(config.uploads_db_path, upload_id, fields)
    if record:
        EVENT_BUS.publish("upload_updated", record_to_event(record))
    return record


def record_to_event(record: UploadRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status,
        "video_path": record.video_path,
        "sequence": record.sequence,
        "error": record.error,
        "youtube_video_id": record.youtube_video_id,
        "updated_at": record.updated_at,
    }


def get_upload_by_path_safe(config: Config, video_path: str) -> UploadRecord | None:
    from .store import get_upload_by_path

    return get_upload_by_path(config.uploads_db_path, video_path)


def _resolve_payload(record: UploadRecord) -> UploadPayload:
    title = record.edited_title or record.default_title or ""
    if record.sequence is not None:
        title = apply_sequence_to_title(title, record.sequence)

    description = record.edited_description or record.default_description or ""

    tags_raw = record.edited_tags or record.default_tags or ""
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    return UploadPayload(title=title, description=description, tags=tags)


def _do_upload(config: Config, upload_id: int) -> None:
    record = get_upload(config.uploads_db_path, upload_id)
    if not record:
        return

    started_at = datetime.now(timezone.utc)
    updated = set_status(config.uploads_db_path, upload_id, "uploading")
    if updated is not None:
        EVENT_BUS.publish("upload_updated", record_to_event(updated))

    try:
        payload = _resolve_payload(record)
        youtube_video_id = perform_upload(
            config,
            video_path=Path(record.video_path),
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            description_path=Path(record.description_path) if record.description_path else None,
            match_id=record.match_id,
            started_at=started_at,
        )
        updated = set_status(
            config.uploads_db_path,
            upload_id,
            "uploaded",
            youtube_video_id=youtube_video_id,
            error=None,
        )
        if updated is not None:
            EVENT_BUS.publish("upload_updated", record_to_event(updated))

        # Optional: archive files after successful upload.
        if config.move_after_upload:
            try:
                config.archive_folder.mkdir(parents=True, exist_ok=True)

                src_video = Path(record.video_path)
                dst_video = config.archive_folder / src_video.name
                if src_video.exists() and not dst_video.exists():
                    shutil.move(str(src_video), str(dst_video))

                new_fields: dict[str, Any] = {}
                if dst_video.exists():
                    new_fields["video_path"] = str(dst_video)

                if record.description_path:
                    src_desc = Path(record.description_path)
                    dst_desc = config.archive_folder / src_desc.name
                    if src_desc.exists() and not dst_desc.exists():
                        shutil.move(str(src_desc), str(dst_desc))
                    if dst_desc.exists():
                        new_fields["description_path"] = str(dst_desc)

                if new_fields:
                    moved = update_upload(config.uploads_db_path, upload_id, new_fields)
                    if moved is not None:
                        EVENT_BUS.publish("upload_updated", record_to_event(moved))
            except Exception as move_err:
                # Don't fail the upload just because archiving failed.
                print(f"[uploads] warning: failed to archive files: {move_err}")
    except Exception as err:
        updated = set_status(
            config.uploads_db_path,
            upload_id,
            "error",
            error=str(err),
        )
        if updated is not None:
            EVENT_BUS.publish("upload_updated", record_to_event(updated))
