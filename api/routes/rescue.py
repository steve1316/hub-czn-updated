from __future__ import annotations

import json
import logging
import re
from functools import cache
from pathlib import Path

from api.frozen_path import add_vribbels_to_path, data_path
add_vribbels_to_path()

from fastapi import APIRouter

try:
    from game_data import CHARACTERS, PARTNERS
except ImportError:
    CHARACTERS = {}
    PARTNERS = {}

router = APIRouter()

LOCAL_FACE_BASE = "/assets/game/faces/bookmark_face_character_map_{res_id}.png"
# The in-game Probability Guide: a 1% 5-star chance per pull, rising by 4.5% a pull from the 58th, and a sure 5-star on the 70th.
SSR_BASE_RATE = 0.01
SOFT_PITY_START = 58
SOFT_PITY_STEP = 0.045
PITY_CAP = 70
# Pool ids with every number masked, so a pool newer than `gacha_banners.json` can borrow the category of a known pool shaped like it.
# `gacha_pickup_combatant_30200` matches the seasonal rate-ups and `gacha_pickup_combatant_1070_1` the Normal ones.
POOL_NUMBERS = re.compile(r"\d+")


def _char_details(res_id: int) -> dict:
    char = CHARACTERS.get(res_id)
    if char:
        return {
            "name": char.get("name", f"#{res_id}"),
            "rarity": char.get("grade", 3),
            "kind": "Combatant",
            "image_url": LOCAL_FACE_BASE.format(res_id=res_id),
        }
    partner = PARTNERS.get(res_id)
    if partner and partner.get("name") != "Unknown":
        return {
            "name": partner.get("name", f"#{res_id}"),
            "rarity": partner.get("grade", 3),
            "kind": "Partner",
            "image_url": LOCAL_FACE_BASE.format(res_id=res_id),
        }
    return {
        "name": f"#{res_id}",
        "rarity": 3,
        "kind": "Unknown",
        "image_url": LOCAL_FACE_BASE.format(res_id=res_id),
    }


@cache
def _banners() -> dict[str, dict]:
    """The generated pool -> {name, pity_group, fifty_fifty} table, or empty when it cannot be read."""
    try:
        return json.loads(data_path("gacha_banners.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logging.getLogger(__name__).warning("Failed to read gacha_banners.json, so rescue categories fall back to pool ids: %s", exc)
        return {}


@cache
def _banners_by_shape() -> dict[str, dict]:
    """The first known pool for each masked pool id."""
    shapes: dict[str, dict] = {}
    for pool_id, entry in _banners().items():
        shapes.setdefault(POOL_NUMBERS.sub("#", pool_id), entry)
    return shapes


def _banner(gacha_id: str) -> tuple[str, str | None, bool]:
    """
    Place a pool in its in-game Rescue Records category.

    Args:
        gacha_id: The pool id from a rescue record.

    Returns:
        The category name, the server pity group its pulls count toward (None when not known), and whether its 5-stars are a 50/50.
    """
    entry = _banners().get(gacha_id) or _banners_by_shape().get(POOL_NUMBERS.sub("#", gacha_id))
    if entry:
        return entry["name"], entry.get("pity_group"), bool(entry.get("fifty_fifty"))
    return gacha_id.replace("_", " ").title(), None, False


def _expand_batch(record: dict) -> list[dict]:
    try:
        rewards = json.loads(record.get("reward", "[]"))
    except (json.JSONDecodeError, TypeError):
        rewards = []
    try:
        prisms = json.loads(record.get("prism", "[]"))
    except (json.JSONDecodeError, TypeError):
        prisms = []

    gacha_id = record.get("gacha_id", "")
    try:
        ts = int(record.get("createAt", 0))
    except (ValueError, TypeError):
        ts = 0

    return [
        {
            "res_id": int(r),
            "gacha_id": gacha_id,
            "timestamp": ts,
            "is_featured": bool(prisms[i]) if i < len(prisms) else False,
        }
        for i, r in enumerate(rewards)
    ]


@cache
def _gap_odds() -> list[float]:
    """
    The chance that the next 5-star lands on each pull after the last one.

    Returns:
        The odds indexed by pull count, from 1 to `PITY_CAP`. Index 0 is unused.
    """
    odds = [0.0]
    still_waiting = 1.0
    for pull in range(1, PITY_CAP + 1):
        rate = 1.0 if pull == PITY_CAP else SSR_BASE_RATE + SOFT_PITY_STEP * max(0, pull - SOFT_PITY_START + 1)
        odds.append(still_waiting * rate)
        still_waiting -= odds[-1]
    return odds


@cache
def _ssr_rate() -> float:
    """
    The average 5-star rate once pity is counted in, which the game lists as 2.14343%.

    Returns:
        The chance of a 5-star per pull.
    """
    return 1 / sum(pull * odds for pull, odds in enumerate(_gap_odds()))


@cache
def _luck_percentile(five_stars: int, pulls: int) -> float | None:
    """
    How lucky a run of pulls was, under the game's pity curve.

    Args:
        five_stars: The 5-stars got.
        pulls: The pulls made, assumed to start right after a 5-star.

    Returns:
        The percent of players expected to get fewer 5-stars than this, counting ties as half. None when there are no pulls.
    """
    if pulls <= 0:
        return None
    gaps = _gap_odds()
    # The chance that the latest 5-star landed on each pull, starting from none yet at pull 0.
    landed = [1.0] + [0.0] * pulls
    at_least = [1.0]
    for _ in range(five_stars + 1):
        nxt = [0.0] * (pulls + 1)
        for start, odds in enumerate(landed):
            if odds:
                for gap in range(1, min(PITY_CAP, pulls - start) + 1):
                    nxt[start + gap] += odds * gaps[gap]
        landed = nxt
        at_least.append(sum(landed))
    fewer = 1 - at_least[five_stars]
    same = at_least[five_stars] - at_least[five_stars + 1]
    return round(max(0.0, fewer + same / 2) * 100, 1)


def _process_records(raw: list[dict], meta: dict | None = None) -> list[dict]:
    """
    Group raw rescue records by banner, compute stats, return API shape.

    Args:
        raw: The stored rescue records.
        meta: The rest of the stored document, with `pity` (server pity by group), `pool_fetches` (when each pool's history was last
            received) and `session_start` (when the latest capture began).

    Returns:
        One entry per banner.
    """
    meta = meta or {}
    server_pity = meta.get("pity") if isinstance(meta.get("pity"), dict) else {}
    fetches = meta.get("pool_fetches") if isinstance(meta.get("pool_fetches"), dict) else {}
    session_start = meta.get("session_start") or 0
    all_pulls = []
    for rec in raw:
        all_pulls.extend(_expand_batch(rec))
    all_pulls.sort(key=lambda p: p["timestamp"])

    banners: dict[tuple[str, str | None, bool], list[dict]] = {}
    for pull in all_pulls:
        banners.setdefault(_banner(pull["gacha_id"]), []).append(pull)

    result = []
    for (banner_name, group, fifty_fifty), pulls in banners.items():
        pool_ids = sorted({p["gacha_id"] for p in pulls if p["gacha_id"]})
        processed_pulls = []
        pity = 0
        pull_number = 0
        five_stars = 0
        four_stars = 0
        wins_50_50 = 0
        losses_50_50 = 0
        guaranteed = False

        for p in pulls:
            pull_number += 1
            pity += 1
            details = _char_details(p["res_id"])
            rarity = details["rarity"]

            pull_entry = {
                "pull_number": pull_number,
                "res_id": p["res_id"],
                "name": details["name"],
                "rarity": rarity,
                "kind": details["kind"],
                "image_url": details["image_url"],
                "pity": min(pity, PITY_CAP),
                "is_featured": p["is_featured"] if rarity >= 5 else False,
                "timestamp": p["timestamp"],
            }

            if rarity >= 5:
                five_stars += 1
                # A loss makes the next 5-star the featured one, so that one is not a 50/50.
                if fifty_fifty:
                    if guaranteed:
                        guaranteed = False
                    elif p["is_featured"]:
                        wins_50_50 += 1
                    else:
                        losses_50_50 += 1
                        guaranteed = True
                pity = 0
            elif rarity >= 4:
                four_stars += 1

            processed_pulls.append(pull_entry)

        total = len(pulls)
        processed_pulls.reverse()

        server_entry = server_pity.get(group) if group else None
        has_server_pity = isinstance(server_entry, dict) and "pity_ssr_count" in server_entry
        refreshed = [int(fetches[g]) for g in pool_ids if g in fetches]
        last_refreshed = max(refreshed) if refreshed else None

        result.append({
            "banner_name": banner_name,
            "pool_ids": pool_ids,
            "pity_current": int(server_entry["pity_ssr_count"]) if has_server_pity else pity,
            "pity_source": "server" if has_server_pity else "computed",
            "last_refreshed": last_refreshed,
            "stale": last_refreshed is None or last_refreshed < session_start,
            "pulls": processed_pulls,
            "stats": {
                "wins_50_50": wins_50_50,
                "losses_50_50": losses_50_50,
                "luck_percentile": _luck_percentile(five_stars, total),
                "ssr_rate": round(_ssr_rate(), 7),
                "total": total,
                "five_star": five_stars,
                "four_star": four_stars,
                "avg_pity_5": round(total / five_stars, 1) if five_stars else 0,
                "avg_pity_4": round(total / four_stars, 1) if four_stars else 0,
                "win_rate_50_50": round(wins_50_50 / (wins_50_50 + losses_50_50), 4) if wins_50_50 + losses_50_50 else 0,
                "resources_spent": total * 160,
            },
        })

    return result


def _latest_rescue_file() -> Path | None:
    """Find the most recently modified rescue_records_*.json in the snapshots folder."""
    try:
        from api.capture.constants import OUTPUT_DIR
        files = sorted(OUTPUT_DIR.glob("rescue_records_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        return files[0] if files else None
    except Exception:
        return None


@router.get("/rescue/records")
def get_rescue_records():
    path = _latest_rescue_file()
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = raw.get("records", []) if isinstance(raw, dict) else raw
        return _process_records(records, raw if isinstance(raw, dict) else None)
    except Exception:
        return []
