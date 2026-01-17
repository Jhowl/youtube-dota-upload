from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class RecentMatch:
    match_id: int
    start_time: int
    duration: int


def fetch_recent_matches(player_id: int) -> list[RecentMatch]:
    url = f"https://api.opendota.com/api/players/{player_id}/recentMatches"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()
    out: list[RecentMatch] = []
    for row in data:
        out.append(
            RecentMatch(
                match_id=int(row["match_id"]),
                start_time=int(row["start_time"]),
                duration=int(row["duration"]),
            )
        )
    return out


def fetch_player_matches(player_id: int, *, limit: int = 200, date_days: int | None = None) -> list[RecentMatch]:
    params: dict[str, Any] = {"limit": limit}
    if date_days is not None:
        params["date"] = int(date_days)

    url = f"https://api.opendota.com/api/players/{player_id}/matches"
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()

    data = res.json()
    out: list[RecentMatch] = []
    for row in data:
        out.append(
            RecentMatch(
                match_id=int(row["match_id"]),
                start_time=int(row["start_time"]),
                duration=int(row["duration"]),
            )
        )
    return out


def fetch_match(match_id: int) -> dict[str, Any]:
    url = f"https://api.opendota.com/api/matches/{match_id}"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    return res.json()


_PATCHES_CACHE: list[dict[str, Any]] | None = None


def fetch_patches() -> list[dict[str, Any]]:
    global _PATCHES_CACHE
    if _PATCHES_CACHE is not None:
        return _PATCHES_CACHE

    url = "https://api.opendota.com/api/constants/patch"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()
    if not isinstance(data, list):
        raise RuntimeError("Unexpected patch constants payload")

    _PATCHES_CACHE = data
    return _PATCHES_CACHE


_HEROES_CACHE: dict[str, Any] | None = None
_ITEMS_CACHE: dict[str, Any] | None = None


def fetch_heroes() -> dict[str, Any]:
    global _HEROES_CACHE
    if _HEROES_CACHE is not None:
        return _HEROES_CACHE
    url = "https://api.opendota.com/api/constants/heroes"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected heroes constants payload")
    _HEROES_CACHE = data
    return _HEROES_CACHE



def fetch_items() -> dict[str, Any]:
    global _ITEMS_CACHE
    if _ITEMS_CACHE is not None:
        return _ITEMS_CACHE
    url = "https://api.opendota.com/api/constants/items"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected items constants payload")
    _ITEMS_CACHE = data
    return _ITEMS_CACHE


def pick_match_for_recording_time(
    matches: list[RecentMatch],
    recording_epoch: int,
    *,
    before_start_sec: int,
    after_end_sec: int,
) -> int | None:
    candidates: list[tuple[int, int]] = []

    for m in matches:
        start = m.start_time
        end = m.start_time + m.duration
        within = (recording_epoch >= start - before_start_sec) and (recording_epoch <= end + after_end_sec)
        if not within:
            continue
        dist = min(abs(recording_epoch - start), abs(recording_epoch - end))
        candidates.append((dist, m.match_id))

    candidates.sort(key=lambda t: t[0])
    return candidates[0][1] if candidates else None
