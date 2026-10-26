"""
Tests for the `enemy_presets` datagen target, on a tiny fixture client written to a temp folder.
"""

from __future__ import annotations

import json

from scripts.datagen.runner import Context
from scripts.datagen.targets import enemy_presets
from tests.scripts.datagen.fixture_client import write_client


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _stat(stat_id: str, stat_def: str, decrease: str) -> dict:
    """
    One `mon_stat` row with only the columns the target reads.

    Args:
        stat_id: The row id, such as "gold_7".
        stat_def: The `stat_def` cell.
        decrease: The `dmg_decrease_rate` cell.

    Returns:
        The row.
    """
    return {"id": stat_id, "stat_def": stat_def, "dmg_decrease_rate": decrease, "stat_atk": "1", "stat_hp": "1"}


# A row for every group, so only the rows a test adds change the outcome.
BASE = [
    _stat("combat_exp_10", "370", "0.2402"),
    _stat("combat_exp_2", "109", "0.4688"),
    _stat("gold_1", "65", "0.4953"),
    _stat("piece_1_1", "73", "0.4953"),
    _stat("hyperspace_1_01", "112", "0.4357"),
    _stat("boss_1_1", "61", "0.4953"),
    _stat("disaster_rank_s01_01", "89", "0.3697"),
    _stat("stat_1", "47", "0.5035"),
]


def _built(tmp_path, rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Run the target over a fixture client and read its output back.

    Args:
        tmp_path: The temp folder to write the client into.
        rows: The `mon_stat` rows.

    Returns:
        The preset groups in file order, and the issue messages.
    """
    ctx = Context(write_client(tmp_path, {enemy_presets.MON_STAT: rows}, {}))
    result = enemy_presets.build(ctx)
    return json.loads(result.files[enemy_presets.OUTPUT_PATH]), [issue.message for issue in result.issues]


def _group(groups: list[dict], name: str) -> list[dict]:
    """
    The presets of one group.

    Args:
        groups: The built groups.
        name: The group name, such as "combat".

    Returns:
        That group's presets.
    """
    return next(group["presets"] for group in groups if group["group"] == name)


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Tests


def test_groups_come_out_in_display_order(tmp_path):
    groups, issues = _built(tmp_path, BASE)
    assert [group["group"] for group in groups] == ["combat", "gold", "piece", "hyperspace", "boss", "disaster"]
    assert issues == []


def test_levels_are_sorted_numerically_and_carry_the_real_decrease(tmp_path):
    groups, _ = _built(tmp_path, BASE)
    assert _group(groups, "combat") == [
        {"label": "Lv2", "def": 109, "dmg_decrease": 0.4688},
        {"label": "Lv10", "def": 370, "dmg_decrease": 0.2402},
    ]


def test_matching_variants_share_one_level(tmp_path):
    rows = BASE + [_stat("piece_2_1", "73", "0.4953"), _stat("piece_1_2", "105", "0.4688")]
    groups, issues = _built(tmp_path, rows)
    assert [preset["label"] for preset in _group(groups, "piece")] == ["Lv1", "Lv2"]
    assert issues == []


def test_variants_that_disagree_keep_the_first_and_warn(tmp_path):
    rows = BASE + [_stat("boss_2_1", "99", "0.4")]
    groups, issues = _built(tmp_path, rows)
    assert _group(groups, "boss") == [{"label": "Lv1", "def": 61, "dmg_decrease": 0.4953}]
    assert any("boss" in message and "Lv1" in message for message in issues)


def test_a_group_with_one_stat_line_collapses_to_all(tmp_path):
    rows = BASE + [_stat(f"hyperspace_1_{level:02d}", "112", "0.4357") for level in range(2, 11)]
    groups, _ = _built(tmp_path, rows)
    assert _group(groups, "hyperspace") == [{"label": "All", "def": 112, "dmg_decrease": 0.4357}]


def test_disaster_keeps_only_the_latest_season(tmp_path):
    rows = BASE + [_stat("disaster_rank_s02_01", "150", "0.35"), _stat("disaster_rank_s02_02", "180", "0.35")]
    groups, issues = _built(tmp_path, rows)
    assert _group(groups, "disaster") == [
        {"label": "R1", "def": 150, "dmg_decrease": 0.35},
        {"label": "R2", "def": 180, "dmg_decrease": 0.35},
    ]
    assert issues == []


def test_a_group_with_no_rows_is_an_error(tmp_path):
    groups, issues = _built(tmp_path, [row for row in BASE if not row["id"].startswith("gold_")])
    assert "gold" not in [group["group"] for group in groups]
    assert any("gold" in message for message in issues)
