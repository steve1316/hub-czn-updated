"""
The Rescue Records categories: which in-game category each rescue pool belongs to, and the server pity group its pulls count toward.

Pool ids alone do not say this reliably. A rate-up pool id like `gacha_pickup_combatant_1062` can be a seasonal rate-up or, with a `_1`
suffix, a Normal rate-up with its own pity, so the client's `gacha_list` is the source of truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes

NAME = "gacha_banners"
OFFLINE = True

BANNERS_PATH = Path("api/data/gacha_banners.json")
GACHA_LIST = "gacha_list@gacha_list.json"
# The in-game category names, which the client keeps only as tab art. Older non-seasonal rate-ups share the seasonal pity, so they share its
# category too.
TYPE_NAMES = {
    "pickup_combatant_seasonal": "Seasonal Combatant Rescue Rate-Up",
    "gacha_type_pickup_combatant": "Seasonal Combatant Rescue Rate-Up",
    "pickup_supporter_seasonal": "Seasonal Partner Rescue Rate-Up",
    "gacha_type_pickup_supporter": "Seasonal Partner Rescue Rate-Up",
    "gacha_type_genal_p_combatant": "Normal Combatant Rescue Rate-Up",
    "gacha_type_genal_p_supporter": "Normal Partner Rescue Rate-Up",
    "gacha_type_general": "Normal Combatant Rescue",
    "gacha_type_general_supporter": "Normal Partner Rescue",
    "gacha_type_card_factor": "Observe Prism Module",
}
# Combatant rate-ups put one featured 5-star against the rest of the pool, so their 5-stars are a 50/50. A partner rate-up has only the one.
FIFTY_FIFTY_TYPES = {"pickup_combatant_seasonal", "gacha_type_pickup_combatant", "gacha_type_genal_p_combatant"}
MARKUP = re.compile(r"<[^>]*>")


def build(ctx: Context) -> TargetResult:
    """
    Generate the pool -> category table.

    Args:
        ctx: The run context.

    Returns:
        The table, a summary of how it differs from the current one, and a warning for each pool type with no category name.
    """
    banners = {}
    unnamed = set()
    for row in ctx.client.rows(GACHA_LIST):
        kind = row.get("link_gacha_type_id")
        # One-off rescues such as the new player selector keep their own in-game title.
        name = TYPE_NAMES.get(kind) or MARKUP.sub("", ctx.client.text(row.get("name")) or "").strip()
        if not name:
            unnamed.add(kind)
            continue
        banners[row["id"]] = {"name": name, "pity_group": row.get("link_gacha_pity_id"), "fifty_fifty": kind in FIFTY_FIFTY_TYPES}
    issues = [Issue("warning", f"{NAME}: pool type {missing} has no category name, so its pools fall back to their ids") for missing in sorted(unnamed)]
    return TargetResult({BANNERS_PATH: json_bytes(dict(sorted(banners.items())))}, summarise(banners, _current_ids()), issues)


def summarise(banners: dict[str, dict], current_ids: set[str]) -> str:
    """
    One line comparing the generated table with the committed one.

    Args:
        banners: The generated pool entries.
        current_ids: The pool ids in the committed file.

    Returns:
        Such as "58 pools in 10 categories (+2, -0)".
    """
    ids = set(banners)
    categories = {entry["name"] for entry in banners.values()}
    return f"{len(ids)} pools in {len(categories)} categories (+{len(ids - current_ids)}, -{len(current_ids - ids)})"


def _current_ids() -> set[str]:
    """The pool ids in the committed table, or none when it does not exist yet."""
    path = REPO_ROOT / BANNERS_PATH
    return set(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else set()
