from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from pathlib import Path

from zoneinfo import ZoneInfo

from .config import Config
from .description import build_match_description
from .notify import send_finished_notification
from .opendota import (
    fetch_heroes,
    fetch_items,
    fetch_match,
    fetch_patches,
    fetch_player_matches,
    fetch_recent_matches,
    pick_match_for_recording_time,
)
from .youtube_uploader import upload_to_youtube


def _hero_name(heroes: dict, hero_id: int) -> str:
    for h in heroes.values():
        if int(h.get("id", -1)) == hero_id:
            return str(h.get("localized_name") or f"Hero {hero_id}")
    return f"Hero {hero_id}"


def _item_name(items: dict, item_id: int) -> str:
    for i in items.values():
        if int(i.get("id", -1)) == item_id:
            return str(i.get("dname") or f"Item {item_id}")
    return f"Item {item_id}"


def _player_from_match(match: dict, account_id: int) -> dict | None:
    for p in match.get("players", []) or []:
        if p.get("account_id") == account_id:
            return p
    return None


def _patch_name_for_match(match: dict, patches: list[dict]) -> str | None:
    patch_id = match.get("patch")
    if patch_id is None:
        return None

    try:
        pid = int(patch_id)
    except Exception:
        return None

    for p in patches:
        if int(p.get("id", -1)) == pid:
            return str(p.get("name"))

    return None


def _build_seo_title(hero: str, patch: str | None, result: str, duration_min: int, match_id: int) -> str:
    parts: list[str] = []
    parts.append(f"{hero} Gameplay")
    if patch:
        parts.append(f"Patch {patch}")
    parts.append(result)
    parts.append(f"{duration_min}min")
    parts.append("Dota 2")
    parts.append(f"Match {match_id}")
    return " | ".join(parts)


def _extract_item_names(player: dict, items: dict) -> list[str]:
    ids = [
        player.get("item_0"),
        player.get("item_1"),
        player.get("item_2"),
        player.get("item_3"),
        player.get("item_4"),
        player.get("item_5"),
        player.get("item_neutral"),
    ]

    out: list[str] = []
    for x in ids:
        if not x:
            continue
        try:
            iid = int(x)
        except Exception:
            continue
        if iid <= 0:
            continue
        out.append(_item_name(items, iid))

    # Dedup while preserving order
    dedup: list[str] = []
    for n in out:
        if n not in dedup:
            dedup.append(n)
    return dedup


def _build_thumbnail_prompt(
    *,
    hero: str,
    patch: str | None,
    result: str,
    duration_min: int,
    score_text: str,
    kda_text: str | None,
    items_text: str | None,
    match_id: int,
) -> str:
    patch_part = f"Patch {patch}" if patch else "Current Patch"

    lines: list[str] = []
    lines.append("Create a YouTube thumbnail for a Dota 2 match video.")
    lines.append(f"Hero: {hero}.")
    lines.append(f"Match result: {result}.")
    lines.append(f"Match length: {duration_min} minutes.")
    lines.append(f"Score: {score_text}.")
    if kda_text:
        lines.append(f"KDA: {kda_text}.")
    if items_text:
        lines.append(f"Key items: {items_text}.")
    lines.append(f"{patch_part}.")
    lines.append(f"Match ID: {match_id}.")
    lines.append(
        "Style: high-contrast esports thumbnail, sharp hero portrait, dynamic action background, "
        "bold readable text, clean composition, 16:9, 1280x720."
    )
    lines.append(
        "Text overlay (few words): '" + hero.upper() + " BUILD' and '" + result.upper() + "' and '" + patch_part.upper() + "'."
    )
    lines.append("Avoid: small text, clutter, watermarks, blurry faces.")

    return " ".join(lines)


def _build_tags(hero: str, patch: str | None, item_names: list[str]) -> list[str]:
    base = [
        "dota 2",
        "dota2",
        f"{hero}",
        f"{hero} gameplay",
        "dota 2 gameplay",
        "dota 2 ranked",
        "dota 2 highlights",
        "dota 2 build",
        "dota 2 items",
        "dota patch",
        "opendota",
    ]

    if patch:
        base.extend([f"dota 2 patch {patch}", f"patch {patch}"])

    # Add up to 10 item tags
    for item in item_names[:10]:
        base.append(item)
        base.append(f"{hero} {item}")

    # Dedup and cap at 450-ish chars is handled by YouTube, but keep reasonable.
    dedup: list[str] = []
    for t in base:
        tt = t.strip()
        if not tt:
            continue
        if tt.lower() in (x.lower() for x in dedup):
            continue
        dedup.append(tt)

    return dedup[:35]


_FILENAME_RE = re.compile(
    r"(?P<y>\d{4})[-_](?P<mo>\d{2})[-_](?P<d>\d{2})[ _-](?P<h>\d{2})[-_](?P<mi>\d{2})[-_](?P<s>\d{2})"
)


def _parse_obs_filename_time_to_utc(path: Path, tz_name: str) -> datetime:
    base = path.stem
    m = _FILENAME_RE.search(base)
    if not m:
        raise RuntimeError(f"Could not parse datetime from filename: {base}")

    year = int(m.group("y"))
    month = int(m.group("mo"))
    day = int(m.group("d"))
    hour = int(m.group("h"))
    minute = int(m.group("mi"))
    second = int(m.group("s"))

    tz = ZoneInfo(tz_name)
    local_dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def _resolve_match_id(config: Config, recording_start_utc: datetime) -> int:
    recording_epoch = int(recording_start_utc.timestamp())

    window = {
        "before_start_sec": config.match_time_before_sec,
        "after_end_sec": config.match_time_after_sec,
    }

    recent = fetch_recent_matches(config.opendota_player_id)
    match_id = pick_match_for_recording_time(recent, recording_epoch, **window)
    if match_id:
        return match_id

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    days_back = int((now_epoch - recording_epoch) / (24 * 60 * 60)) + 2
    days_back = max(1, min(days_back, 3650))

    older = fetch_player_matches(config.opendota_player_id, limit=200, date_days=days_back)
    match_id = pick_match_for_recording_time(older, recording_epoch, **window)
    if match_id:
        return match_id

    raise RuntimeError(
        f"No match found near recording time ({recording_start_utc.isoformat()}Z). "
        f"Window start-{config.match_time_before_sec}s/end+{config.match_time_after_sec}s. "
        f"Tried recentMatches and players/matches?date={days_back}."
    )


def _description_path(video_path: Path) -> Path:
    return video_path.with_suffix(".txt")


def process_video(config: Config, video_path: Path) -> None:
    started_at = datetime.now(timezone.utc)

    match_id: int | None = None
    youtube_video_id: str | None = None
    description_path: Path | None = None

    try:
        recording_start_utc = _parse_obs_filename_time_to_utc(video_path, config.recording_tz)
        match_id = _resolve_match_id(config, recording_start_utc)

        match = fetch_match(match_id)
        heroes = fetch_heroes()
        items = fetch_items()
        patches = fetch_patches()

        description = build_match_description(
            recording_start_utc=recording_start_utc,
            player_account_id=config.opendota_player_id,
            match=match,
            heroes=heroes,
            items=items,
        )

        player = _player_from_match(match, config.opendota_player_id)
        hero = _hero_name(heroes, int(player.get("hero_id", 0))) if player else "Dota 2"
        patch_name = _patch_name_for_match(match, patches)
        player_is_radiant = bool(player) and int(player.get("player_slot", 0) or 0) < 128
        radiant_win = bool(match.get("radiant_win"))
        result = "Win" if (radiant_win if player_is_radiant else not radiant_win) else "Loss"
        duration_min = max(1, int(int(match.get("duration", 0)) / 60))

        item_names = _extract_item_names(player, items) if player else []

        score_text = f"Radiant {int(match.get('radiant_score', 0))} - {int(match.get('dire_score', 0))} Dire"
        kda_text = None
        if player:
            kda_text = f"{int(player.get('kills', 0))}/{int(player.get('deaths', 0))}/{int(player.get('assists', 0))}"

        items_text = ", ".join(item_names[:8]) if item_names else None

        title = _build_seo_title(hero, patch_name, result, duration_min, int(match.get("match_id") or match_id))

        # SEO: add extra sections to description
        extra_lines: list[str] = []
        extra_lines.append("")
        extra_lines.append("Video")
        extra_lines.append(f"Hero: {hero}")
        if patch_name:
            extra_lines.append(f"Patch: {patch_name}")
        if item_names:
            extra_lines.append("Items: " + ", ".join(item_names[:12]))
        extra_lines.append(f"Match: https://www.opendota.com/matches/{match_id}")
        extra_lines.append("\n#dota2 #dota #opendota")

        match_id_for_prompt = int(match.get("match_id") or match_id)
        thumbnail_prompt = _build_thumbnail_prompt(
            hero=hero,
            patch=patch_name,
            result=result,
            duration_min=duration_min,
            score_text=score_text,
            kda_text=kda_text,
            items_text=items_text,
            match_id=match_id_for_prompt,
        )

        extra_lines.append("")
        extra_lines.append("Thumbnail Prompt")
        extra_lines.append(thumbnail_prompt)

        full_description = description + "\n".join(extra_lines) + "\n"

        description_path = _description_path(video_path)
        description_path.write_text(full_description, encoding="utf-8")

        seo_tags = _build_tags(hero, patch_name, item_names)

        if not config.dry_run:
            print(f"[upload:start] {video_path.name} -> YouTube")
            youtube_video_id = upload_to_youtube(
                config,
                file_path=str(video_path),
                title=title,
                description=full_description,
                tags=seo_tags,
            )
            print(f"[upload:done] videoId={youtube_video_id}")

        try:
            send_finished_notification(
                config,
                status="success",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                video_path=str(video_path),
                description_path=str(description_path) if description_path else None,
                match_id=match_id,
                youtube_video_id=youtube_video_id,
            )
        except Exception as notify_err:
            print(f"[notify:error] {notify_err}")

        print(f"[done] {video_path}")

    except Exception as err:
        try:
            send_finished_notification(
                config,
                status="error",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                video_path=str(video_path),
                description_path=str(description_path) if description_path else None,
                match_id=match_id,
                youtube_video_id=youtube_video_id,
                error=str(err),
            )
        except Exception as notify_err:
            print(f"[notify:error] {notify_err}")

        print(f"[process:error] {video_path} {err}")
