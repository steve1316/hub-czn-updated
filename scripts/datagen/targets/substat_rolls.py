"""
Substat roll ranges: the max and min a Memory Fragment substat can roll, which Gear Score is measured against.

The client's `piece_option` table lists every substat in its `random_option` group, with the values each rarity can roll. Three
literals in `api/game_data/constants.py` are regenerated: `STATS` (the Legendary range Gear Score is measured against),
`SUBSTAT_ROLLS_BY_RARITY` (each rarity's own range, for roll quality and potential) and `MAX_LEVEL_PER_RARITY` (the top level of each
rarity in `piece_reinforce`). Display names and the percent flag are the app's own and are kept. A stat with no substat row (the element
damage stats are main stats only) gets a 0.0 range, which scores as zero.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.game_data.constants import LEGENDARY, STATS
from scripts.datagen.client import parse_list
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, replace_literal

NAME = "substat_rolls"
OFFLINE = True

CONSTANTS_PATH = Path("api/game_data/constants.py")
TS_PATH = Path("src/lib/substat-rolls.ts")

PIECE_OPTION_TABLE = "piece_option@piece_option.json"
REINFORCE_TABLE = "piece_reinforce@piece_reinforce.json"
SUBSTAT_GROUP = "random_option"
# The client's column prefix for each rarity digit in a piece res_id. Unique pieces have no digit of their own and roll like Legendary.
RARITY_COLUMNS = {1: "common", 2: "uncommon", 3: "rare", 4: "legend"}

# A reinforce row id, such as `reinforce_rare_4`.
_REINFORCE_ID = re.compile(r"^reinforce_([a-z]+)_(\d+)$")


def build(ctx: Context) -> TargetResult:
    """
    Generate the roll range tables and the max level of each rarity from the client.

    Args:
        ctx: The run context.

    Returns:
        The constants module, a summary, and a warning for any client substat the app has no name for.

    Raises:
        ValueError: When the reinforce table is missing or a rarity has no levels in it.
    """
    by_rarity: dict[str, dict[int, tuple[float, float]]] = {}
    for row in ctx.client.rows(PIECE_OPTION_TABLE):
        if row.get("group") != SUBSTAT_GROUP:
            continue
        for rarity, prefix in RARITY_COLUMNS.items():
            values = [float(value) for value in parse_list(row.get(f"{prefix}_value"))]
            if values:
                by_rarity.setdefault(row["link_stat_list_id"], {})[rarity] = (max(values), min(values))
    ranges = {stat_id: rolls[LEGENDARY] for stat_id, rolls in by_rarity.items() if LEGENDARY in rolls}

    top_levels: dict[str, int] = {}
    for row in ctx.client.rows(REINFORCE_TABLE):
        if match := _REINFORCE_ID.match(row.get("id", "")):
            top_levels[match[1]] = max(top_levels.get(match[1], 0), int(match[2]))
    missing = [prefix for prefix in RARITY_COLUMNS.values() if prefix not in top_levels]
    if missing:
        raise ValueError(f"{REINFORCE_TABLE} has no levels for {', '.join(missing)}")
    max_levels = {rarity: top_levels[prefix] for rarity, prefix in RARITY_COLUMNS.items()}

    issues = [Issue("warning", f"{NAME}: client substat {stat_id} has no entry in STATS") for stat_id in ranges if stat_id not in STATS]
    module = (REPO_ROOT / CONSTANTS_PATH).read_text(encoding="utf-8")
    module = replace_literal(module, "STATS", _render(ranges), CONSTANTS_PATH)
    rarity_lines = [f'"{stat_id}": {by_rarity[stat_id]}' for stat_id in STATS if stat_id in by_rarity]
    module = replace_literal(module, "SUBSTAT_ROLLS_BY_RARITY", _render_dict("SUBSTAT_ROLLS_BY_RARITY", rarity_lines), CONSTANTS_PATH)
    levels = [f"{rarity}: {level}" for rarity, level in max_levels.items()]
    module = replace_literal(module, "MAX_LEVEL_PER_RARITY", _render_dict("MAX_LEVEL_PER_RARITY", levels), CONSTANTS_PATH)
    files = {CONSTANTS_PATH: module.encode("utf-8"), TS_PATH: _render_ts(ranges).encode("utf-8")}
    return TargetResult(files, f"{len(ranges)} substats", issues)


def _render_dict(name: str, entries: list[str]) -> str:
    """
    A dict literal with one entry per line.

    Args:
        name: The literal's name.
        entries: Each entry's `key: value` source.

    Returns:
        Python source for the assignment, ending with a newline.
    """
    return "\n".join([f"{name} = {{"] + [f"    {entry}," for entry in entries]) + "\n}\n"


def _render(ranges: dict[str, tuple[float, float]]) -> str:
    """
    The `STATS` literal, laid out the way the file has always been.

    Args:
        ranges: stat id -> (max roll, min roll) from the client.

    Returns:
        Python source for the assignment, ending with a newline.
    """
    lines = ["STATS = {"]
    for stat_id, (name, short, is_percent, _, _) in STATS.items():
        high, low = ranges.get(stat_id, (0.0, 0.0))
        lines.append(f'    "{stat_id}": ("{name}", "{short}", {is_percent}, {high}, {low}),')
    return "\n".join(lines) + "\n}\n"


def _render_ts(ranges: dict[str, tuple[float, float]]) -> str:
    """
    The frontend copy: one entry per substat that has a roll range, in `STATS` order.

    Args:
        ranges: stat id -> (max roll, min roll) from the client.

    Returns:
        TypeScript source for `src/lib/substat-rolls.ts`.
    """
    lines = [
        "// Generated by `python -m scripts.datagen substat_rolls`. Do not edit by hand.",
        "",
        "/** The roll range of one substat. */",
        "export interface SubstatRoll {",
        "  /** Stat name as shown in the app. */",
        "  name: string",
        "  /** Highest single roll. */",
        "  max: number",
        "  /** Lowest single roll. */",
        "  min: number",
        "  /** True when the value is a percentage. */",
        "  percent: boolean",
        "}",
        "",
        "/** Every stat that can roll as a substat, with its roll range. */",
        "export const SUBSTAT_ROLLS: SubstatRoll[] = [",
    ]
    for stat_id, (name, _, is_percent, _, _) in STATS.items():
        if stat_id in ranges:
            high, low = ranges[stat_id]
            lines.append(f'  {{ name: "{name}", max: {high:g}, min: {low:g}, percent: {str(is_percent).lower()} }},')
    return "\n".join(lines) + "\n]\n"
