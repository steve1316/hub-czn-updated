"""
Tests for the `substat_rolls` datagen target, on a tiny fixture client written to a temp folder.

The STATS table in `constants.py` gets its roll ranges from the client's `random_option` rows. Names and flags stay as written. The
per-rarity ranges and the max level of each rarity are generated next to it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.datagen.runner import Context
from scripts.datagen.targets import substat_rolls

# The highest reinforce level of each rarity in the fixture, matching the live client.
REINFORCE_TOPS = {"common": 2, "uncommon": 3, "rare": 4, "legend": 5, "unique": 5}


def _row(stat_id: str, values: str) -> dict:
    """
    One `random_option` row with only the columns the target reads.

    Args:
        stat_id: The stat list id.
        values: The `legend_value` cell.

    Returns:
        The row.
    """
    return {"group": "random_option", "id": f"random_{stat_id}", "link_stat_list_id": stat_id, "legend_value": values, "unique_value": values}


def _context(root: Path, rows: list[dict]) -> Context:
    """
    A run context over a fixture client.

    Args:
        root: The temp folder.
        rows: The `piece_option` rows.

    Returns:
        The context.
    """
    (root / "db").mkdir()
    (root / "text" / "en").mkdir(parents=True)
    (root / "db" / "piece_option@piece_option.json").write_text(json.dumps(rows), encoding="utf-8")
    reinforce = [{"id": f"reinforce_{rarity}_{level}"} for rarity, top in REINFORCE_TOPS.items() for level in range(top + 1)]
    (root / "db" / "piece_reinforce@piece_reinforce.json").write_text(json.dumps(reinforce), encoding="utf-8")
    (root / "text" / "en" / "text.json").write_text("[]", encoding="utf-8")
    return Context(root)


def _stats(ctx: Context, name: str = "STATS") -> dict:
    """
    Run the target and read one generated literal back out of the module.

    Args:
        ctx: The run context.
        name: The literal to read.

    Returns:
        Its value.
    """
    source = substat_rolls.build(ctx).files[substat_rolls.CONSTANTS_PATH].decode("utf-8")
    for node in ast.parse(source.lstrip("﻿")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"no {name} in output")


def test_roll_range_comes_from_the_client(tmp_path):
    """Max and min are the largest and smallest legend roll, and names are kept."""
    stats = _stats(_context(tmp_path, [_row("S_ATK_INC_ADD_OUT", "[5,6,7,9]"), _row("S_CRI_INC_ADD", "[1.2,2.5]")]))
    assert stats["S_ATK_INC_ADD_OUT"] == ("Flat ATK", "Flat ATK", False, 9.0, 5.0)
    assert stats["S_CRI_INC_ADD"] == ("CRate", "CRate", True, 2.5, 1.2)


def test_stat_with_no_substat_row_has_no_roll_range(tmp_path):
    """Element damage is a main stat only, so it scores zero as a substat."""
    stats = _stats(_context(tmp_path, [_row("S_ATK_INC_ADD_OUT", "[5,8]")]))
    assert stats["S_RED_DMG_RATE_INC_ADD"] == ("Passion DMG%", "Passion", True, 0.0, 0.0)


def test_unknown_client_stat_is_reported(tmp_path):
    """A new substat the app has no name for is a warning, not a silent drop."""
    result = substat_rolls.build(_context(tmp_path, [_row("S_NEW_STAT", "[1,2]")]))
    assert any("S_NEW_STAT" in issue.message for issue in result.issues)


def test_ts_copy_lists_only_real_substats(tmp_path):
    """The frontend copy has one entry per substat with a roll range, in STATS order."""
    ctx = _context(tmp_path, [_row("S_ATK_INC_ADD_OUT", "[5,8]"), _row("S_ATK_INC_RATE_OUT", "[0.8,1.3]")])
    text = substat_rolls.build(ctx).files[substat_rolls.TS_PATH].decode("utf-8")
    assert '{ name: "Flat ATK", max: 8, min: 5, percent: false }' in text
    assert '{ name: "ATK%", max: 1.3, min: 0.8, percent: true }' in text
    assert "Passion" not in text


def test_each_rarity_gets_its_own_roll_range(tmp_path):
    """A Rare Flat ATK rolls 4 to 7 while a Legendary one rolls 5 to 8."""
    row = _row("S_ATK_INC_ADD_OUT", "[5,6,7,8]") | {"common_value": "[2,3,4,5]", "uncommon_value": "[3,4,5,6]", "rare_value": "[4,5,6,7]"}
    ranges = _stats(_context(tmp_path, [row]), "SUBSTAT_ROLLS_BY_RARITY")
    assert ranges["S_ATK_INC_ADD_OUT"] == {1: (5.0, 2.0), 2: (6.0, 3.0), 3: (7.0, 4.0), 4: (8.0, 5.0)}


def test_max_level_comes_from_the_reinforce_table(tmp_path):
    """Each level adds one roll, so the top reinforce level is how many rolls a piece gets after it drops."""
    levels = _stats(_context(tmp_path, [_row("S_ATK_INC_ADD_OUT", "[5,8]")]), "MAX_LEVEL_PER_RARITY")
    assert levels == {1: 2, 2: 3, 3: 4, 4: 5}
