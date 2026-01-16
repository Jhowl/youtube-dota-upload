from __future__ import annotations

from datetime import datetime
from typing import Any


def _format_duration(total_seconds: int) -> str:
    m = total_seconds // 60
    s = total_seconds % 60
    return f"{m}:{s:02d}"


def _hero_name(heroes: dict[str, Any], hero_id: int) -> str:
    for h in heroes.values():
        if int(h.get("id", -1)) == hero_id:
            return str(h.get("localized_name") or f"Hero {hero_id}")
    return f"Hero {hero_id}"


def _item_name(items: dict[str, Any], item_id: int) -> str:
    for i in items.values():
        if int(i.get("id", -1)) == item_id:
            return str(i.get("dname") or f"Item {item_id}")
    return f"Item {item_id}"


def _format_item_list(items: dict[str, Any], ids: list[int | None]) -> str:
    names: list[str] = []
    for item_id in ids:
        if not item_id or int(item_id) <= 0:
            continue
        names.append(_item_name(items, int(item_id)))
    return ", ".join(names) if names else "—"


def build_match_description(
    *,
    recording_start_utc: datetime,
    player_account_id: int,
    match: dict[str, Any],
    heroes: dict[str, Any],
    items: dict[str, Any],
) -> str:
    match_id = int(match.get("match_id") or 0)
    match_start = datetime.utcfromtimestamp(int(match.get("start_time") or 0))

    winner = "Radiant" if bool(match.get("radiant_win")) else "Dire"

    lines: list[str] = []
    lines.append(f"Match ID: {match_id}")
    lines.append(f"Recording start (UTC): {recording_start_utc.isoformat()}Z")
    lines.append(f"Match start (UTC): {match_start.isoformat()}Z")
    lines.append(f"Duration: {_format_duration(int(match.get('duration', 0)))}")
    lines.append(f"Winner: {winner}")
    lines.append(
        f"Score: Radiant {int(match.get('radiant_score', 0))} - {int(match.get('dire_score', 0))} Dire"
    )

    player = None
    for p in match.get("players", []) or []:
        if p.get("account_id") == player_account_id:
            player = p
            break

    if player:
        lines.append("")
        lines.append("Player")
        lines.append(f"Account ID: {player_account_id}")
        lines.append(f"Hero: {_hero_name(heroes, int(player.get('hero_id', 0)))}")
        lines.append(
            f"K/D/A: {int(player.get('kills', 0))}/{int(player.get('deaths', 0))}/{int(player.get('assists', 0))}"
        )

        lines.append("")
        lines.append("Items")
        lines.append(
            "Main: "
            + _format_item_list(
                items,
                [
                    player.get("item_0"),
                    player.get("item_1"),
                    player.get("item_2"),
                    player.get("item_3"),
                    player.get("item_4"),
                    player.get("item_5"),
                ],
            )
        )
        lines.append(
            "Backpack: "
            + _format_item_list(
                items,
                [player.get("backpack_0"), player.get("backpack_1"), player.get("backpack_2")],
            )
        )
        lines.append("Neutral: " + _format_item_list(items, [player.get("item_neutral")]))

    lines.append("")
    lines.append("Links")
    lines.append(f"OpenDota match: https://www.opendota.com/matches/{match_id}")

    return "\n".join(lines) + "\n"
