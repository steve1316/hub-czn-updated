"""
Gear presets: each combatant's recommended Memory Fragment sets, main stats and substats.

The client's `piece_valid_setting` table holds the game's own recommendation per combatant. Only the `_RAW` table in
`api/game_data/char_presets.py` is regenerated. The functions below it in that file are left alone. The Android app
gets the same presets as JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from api.game_data import char_presets
from api.game_data.constants import STATS
from scripts.datagen import roster
from scripts.datagen.client import parse_list
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult

NAME = "char_presets"
OFFLINE = True

PRESETS_PATH = Path("api/game_data/char_presets.py")
ANDROID_PATH = Path("android-app/app/src/main/assets/char_presets.json")

COMBATANT_TABLE = "char_base@char_combatant.json"
SETTING_TABLE = "piece_valid_setting@piece_valid_setting.json"

# The `_RAW` literal in char_presets.py, from its opening line to the closing brace on its own line.
_RAW_BLOCK = re.compile(r"_RAW: dict\[int, dict\] = \{\n.*?\n\}\n", re.DOTALL)
_SET_OPTION = re.compile(r"set_public_0*(\d+)$")


def build(ctx: Context) -> TargetResult:
    """
    Generate the presets module's table and the Android copy.

    Args:
        ctx: The run context.

    Returns:
        Both files, a summary, and any unmapped stat or set ids as issues.
    """
    combatants = ctx.client.by_id(COMBATANT_TABLE)
    settings = ctx.client.by_id(SETTING_TABLE)
    issues: list[Issue] = []
    raw: dict[int, dict] = {}
    for res_id, character in sorted(roster.combatants().items()):
        setting = settings.get(combatants.get(str(res_id), {}).get("link_piece_valid_setting_id", ""))
        if setting is None:
            issues.append(Issue("warning", f"{NAME}: no piece_valid_setting row for {character['name']} ({res_id})"))
            continue
        raw[res_id] = {
            "sets": [int(match.group(1)) for option in parse_list(setting.get("piece_preset_1_link_piece_set_option_id")) if (match := _SET_OPTION.match(option))],
            "main_4": _stats(setting, "valid_option_piece_4_link_stat_list_id", res_id, issues),
            "main_5": _stats(setting, "valid_option_piece_5_link_stat_list_id", res_id, issues),
            "main_6": _stats(setting, "valid_option_piece_6_link_stat_list_id", res_id, issues),
            "substats": _stats(setting, "valid_option_list_link_stat_list_id", res_id, issues),
        }

    module = (REPO_ROOT / PRESETS_PATH).read_text(encoding="utf-8-sig")
    if not _RAW_BLOCK.search(module):
        raise ValueError(f"could not find the _RAW table in {PRESETS_PATH}")
    module = _RAW_BLOCK.sub(lambda _: _render(raw), module, count=1)
    return TargetResult(
        {PRESETS_PATH: module.encode("utf-8"), ANDROID_PATH: json.dumps(_android(raw), indent=2).encode("utf-8")},
        f"{len(raw)} presets",
        issues,
    )


def _stats(setting: dict, column: str, res_id: int, issues: list[Issue]) -> list[str]:
    """
    One stat list from a setting row, as the app's stat names, in the client's order.

    Args:
        setting: The piece_valid_setting row.
        column: The list column to read.
        res_id: The combatant, for messages.
        issues: Unknown stat ids are reported here.

    Returns:
        The stat names. Unknown ids are dropped.
    """
    names = []
    for stat_id in parse_list(setting.get(column)):
        if stat_id in STATS:
            names.append(STATS[stat_id][0])
        else:
            issues.append(Issue("error", f"{NAME}: {res_id} {column} has an unknown stat id {stat_id}"))
    return names


def _render(raw: dict[int, dict]) -> str:
    """
    The `_RAW` literal, laid out the way the file has always been.

    Args:
        raw: res_id -> preset.

    Returns:
        Python source for the assignment, ending with a newline.
    """
    lines = ["_RAW: dict[int, dict] = {"]
    for res_id, preset in raw.items():
        lines += [
            f"    {res_id}: {{",
            f'        "sets":    {preset["sets"]!r},',
            f'        "main_4":  {preset["main_4"]!r},',
            f'        "main_5":  {preset["main_5"]!r},',
            f'        "main_6":  {preset["main_6"]!r},',
            f'        "substats":{preset["substats"]!r},',
            "    },",
        ]
    return "\n".join(lines) + "\n}\n"


def _android(raw: dict[int, dict]) -> dict[str, dict]:
    """
    The Android copy, which is `get_char_preset()` for every combatant.

    Args:
        raw: res_id -> preset, not yet written to disk.

    Returns:
        res_id string -> the expanded preset with weights.
    """
    saved = char_presets._RAW
    char_presets._RAW = raw
    try:
        return {str(res_id): char_presets.get_char_preset(res_id) for res_id in raw}
    finally:
        char_presets._RAW = saved
