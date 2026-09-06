"""Auto-extract Memory Fragment set entries for api/game_data/sets.py::SETS.

This is *assisted* extraction. id, name, piece count, icon and the machine-readable stat bonuses are
auto-resolved. Conditional bonuses come out as the client's own English description, which is often
longer than the one-line summary the table keeps, so those are marked `# TODO: review` for a human to
shorten before paste. Anything the table cannot represent is reported on stderr rather than dropped.

Shards read:
    db/piece_set_option@piece_set_option.json   the set table, with its set2/set4/set6 tiers
    db/item_piece@item_piece.json               joins a 7-digit piece res_id to a set option id
    text/en/text.json                           display names and bonus descriptions

Only sets that item_piece actually links to are emitted. The client table also holds faction and
per-combatant sets, plus sets with no pieces in the game yet, and none of those are Memory Fragments
a player can own.

Usage:
    python scripts/extract_sets.py <output_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

# The client wraps text in its own markup, e.g. <color_ego_norms_light>Order</>. scripts/ko_pipeline/
# detemplatize.py is the fuller version of this, but it also rewrites $term$ and {cal} markup that set
# descriptions do not use, and importing it would cost this standalone script its stdlib-only imports.
MARKUP = re.compile(r"<[^>]+>")

# The client's stat identifiers, mapped to the names the optimizer scores in calculate_build_stats.
# api/game_data/constants.py::STATS maps the same client ids for substat display, but it calls crit
# damage "CDmg" where SETS and the optimizer both use "Crit DMG", so this stays a separate map.
# S_CRI_INC_ADD is unmapped on purpose: the optimizer has no crit rate arm for set bonuses. A set
# using it is reported on stderr rather than quietly downgraded to conditional.
STAT_LINKS = {
    "S_ATK_INC_RATE_OUT": "ATK%",
    "S_DEF_INC_RATE_OUT": "DEF%",
    "S_HP_INC_RATE_OUT": "HP%",
    "S_CRI_DMG_RATE_INC_ADD": "Crit DMG",
}

TIERS = (2, 4, 6)


class Bonus(NamedTuple):
    """One set2/set4/set6 tier read off a client set row."""

    text: str
    stat: str | None = None
    value: int = 0


def _load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _normalise(text: str) -> str:
    """
    Flatten a client description into one line of plain ASCII.

    The client mixes U+2019 and ASCII apostrophes, separates clauses with `<br>`, and wraps attribute
    names in markup that means nothing outside its own UI.

    Args:
        text: The raw description or name from text.json.

    Returns:
        The same string as one line of plain ASCII, with ` | ` in place of line breaks.
    """
    flat = text.replace("\u2019", "'").replace("<br>", " | ")
    return MARKUP.sub("", flat).strip()


def _tier_bonus(row: dict, tier: int, text: dict[str, str]) -> Bonus | None:
    """
    Read one set2/set4/set6 tier off a client set row.

    Args:
        row: A `piece_set_option` row.
        tier: Which tier to read, 2, 4 or 6.
        text: The English text catalogue, keyed by text id.

    Returns:
        The tier's bonus, with `stat` and `value` filled in when it is a stat the optimizer scores,
        or None when the set has no bonus at that tier.
    """
    kind = row.get(f"set{tier}_type")
    if not kind or kind == "none":
        return None

    description = _normalise(text.get(row.get(f"set{tier}_description", ""), ""))
    if kind != "SET_TYPE_STAT":
        return Bonus(description)

    link = row.get(f"set{tier}_option_multiple_link")
    stat = STAT_LINKS.get(link)
    if stat is None:
        _warn(f"{row['id']} set{tier} is a stat bonus on {link}, which the optimizer cannot score. "
              f"It will read as conditional and contribute nothing.")
        return Bonus(description)
    return Bonus(description, stat, int(row[f"set{tier}_value"]))


def extract_sets(output_dir: Path) -> dict[int, dict]:
    """
    Build the SETS entries for every Memory Fragment set a player can own.

    Args:
        output_dir: Root of the extracted client data, the folder holding `db/` and `text/`.

    Returns:
        A mapping of numeric set id to a SETS-shaped entry, ordered by set id.

    Raises:
        FileNotFoundError: If any of the three shards is missing from the dump.
    """
    db = Path(output_dir) / "db"
    text = {r["id"]: r["text"] for r in _load_json(Path(output_dir) / "text" / "en" / "text.json")}
    rows = {r["id"]: r for r in _load_json(db / "piece_set_option@piece_set_option.json")}

    # The last three digits of a piece res_id are its set id, which is how the app decodes captures.
    owned = {int(str(i["id"])[4:]): i["link_piece_set_option_id"]
             for i in _load_json(db / "item_piece@item_piece.json") if len(str(i["id"])) == 7}

    sets: dict[int, dict] = {}
    for set_id in sorted(owned):
        row = rows.get(owned[set_id])
        if row is None:
            continue
        tiers = {tier: bonus for tier in TIERS if (bonus := _tier_bonus(row, tier, text))}
        if not tiers:
            continue

        # The highest tier the set defines is the one the table calls its piece count. A lower stat
        # tier becomes the two_piece sub-bonus the optimizer applies at 2 pieces.
        main_tier = max(tiers)
        main = tiers[main_tier]
        if main_tier == 6:
            _warn(f"{row['id']} has a 6-piece tier, which SETS cannot represent. Paste it and the "
                  f"table's own tests will reject it.")

        entry = {
            "name": _normalise(text.get(row["name"], f"Unknown({set_id})")),
            "pieces": main_tier,
            "bonus": main.text,
            "type": "stat" if main.stat else "conditional",
        }
        if main.stat:
            entry["stat"] = main.stat
            entry["value"] = main.value
        low = tiers.get(2)
        if main_tier >= 4 and low and low.stat:
            entry["two_piece"] = {"stat": low.stat, "value": low.value}
        if row.get("set_icon") and row["set_icon"] != "none":
            entry["icon_path"] = f"/assets/pieces/icon_piece_set_{set_id:03d}.png"
        sets[set_id] = entry
    return sets


def _format_entry(set_id: int, entry: dict) -> str:
    """
    Render one entry as a paste-ready line for api/game_data/sets.py.

    Args:
        set_id: The numeric set id, the dict key in SETS.
        entry: The entry produced by `extract_sets`.

    Returns:
        A single `id: {...},` line, with a review marker when the bonus text needs shortening.
    """
    body = ", ".join(
        f'"{key}": ' + (f"_ICON.format({set_id})" if key == "icon_path" else repr(value))
        for key, value in entry.items()
    )
    todo = "" if "stat" in entry else "  # TODO: review, shorten the bonus text"
    return f"    {set_id}: {{{body}}},{todo}"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python scripts/extract_sets.py <output_dir>", file=sys.stderr)
        return 2
    sets = extract_sets(Path(argv[1]))
    print(f"# {len(sets)} sets extracted from {argv[1]}")
    for set_id, entry in sets.items():
        print(_format_entry(set_id, entry))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
