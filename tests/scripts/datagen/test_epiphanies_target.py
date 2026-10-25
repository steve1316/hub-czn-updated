"""
Tests for the `epiphanies` datagen target.

The pure helpers are checked on inline data. `build()` runs against a tiny fixture client written to a temp folder, with
no earlier output on disk, to pin which `r_spark` rows become entries and how they read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.datagen.runner import Context
from scripts.datagen.targets import epiphanies

TEXT = {
    "r_spark@r_spark_description@morale": "$Morale$ <cc>#ev_0#</>",
    "r_spark@r_spark_description@draw": "$Draw$ <cc>#ev_0#</>",
    "r_spark@r_spark_description@weak": "Always $Attack Weakness$",
    "r_spark@r_spark_description@hand": "If <cc>8</> or more cards are in hand,<br>change Cost to <cc>0</>",
    "fate_god_type_define@name@vitor": "Vytor\u2019s Epiphany",
    "base_class_define@class_name@striker": "Striker",
    "base_class_define@class_name@knight": "Vanguard",
    "tooltip@title@talent_weakpoint": "Weakness Attack",
}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _row(row_id: str, description: str, cost_min: str, cost_max: str, **fields) -> dict:
    """
    One `r_spark` row with the columns the target reads.

    Args:
        row_id: The row id.
        description: The text key suffix after `r_spark@r_spark_description@`.
        cost_min: `target_card_cost_min`.
        cost_max: `target_card_cost_max`.
        **fields: Columns to override.

    Returns:
        The row.
    """
    row = {
        "id": row_id,
        "god_type": "none",
        "rarity": "R_SPARK_RARITY_COMMON",
        "description": f"r_spark@r_spark_description@{description}",
        "add_link_skill_eff_id": f"[{row_id}_0]",
        "add_talent": "[]",
        "target_card_category": "[CARD_ATK,CARD_SKILL]",
        "target_link_base_class_define_id": "[striker,vanguard]",
        "target_card_cost_min": cost_min,
        "target_card_cost_max": cost_max,
        "target_card_include_talent": "[]",
        "target_card_exclude_talent": "[]",
        "r_spark_tag": "[]",
        "r_spark_exclude_tag": "[]",
        "link_extra_tag_id": "[]",
        "r_spark_ratio": "10",
    }
    row.update(fields)
    return row


def _write_client(root: Path) -> None:
    """
    Write a fixture client with a few common rows, one card-specific copy, one disabled row and two divine rows.

    Args:
        root: The folder to write `db/` and `text/` into.
    """
    rows = [
        _row("c00000", "morale", "0", "0"),
        _row("c00001", "morale", "1", "1"),
        _row("c00004", "morale", "4", "99"),
        # The X bucket repeats the cost 0 row, effect included.
        _row("c00005", "morale", "-1", "-1", add_link_skill_eff_id="[c00000_0]"),
        _row("c_30047_00004", "morale", "4", "99", r_spark_tag="[nine_exhaust]", add_link_skill_eff_id="[c00004_0]"),
        _row("c14001", "morale", "1", "1", r_spark_ratio="0"),
        _row("pick_fail_default_r_spark", "draw", "-1", "1", r_spark_ratio="0", target_card_category="[]", target_link_base_class_define_id="[]"),
        _row("add_r_spark_vitor_06", "weak", "-1", "99", god_type="VITOR", rarity="R_SPARK_RARITY_UNIQUE", add_link_skill_eff_id="[]",
             add_talent="[TALENT_WEAKPOINT]", target_card_category="[CARD_ATK]", target_link_base_class_define_id="[]", r_spark_ratio="1000"),
        _row("assault_r_spark_vitor_7", "hand", "1", "99", god_type="VITOR", rarity="R_SPARK_RARITY_UNIQUE", add_link_skill_eff_id="[]",
             target_card_category="[]", target_link_base_class_define_id="[]", r_spark_ratio="1500"),
    ]
    effects = [{"id": f"{row_id}_0", "eff": "SKILL_EFF_BUFF", "eff_value": value} for row_id, value in (("c00000", "1"), ("c00001", "1"), ("c00004", "2"))]
    effects.append({"id": "pick_fail_default_r_spark_0", "eff": "SKILL_EFF_DRAW", "eff_value": "1"})
    tables = {
        "r_spark@r_spark.json": rows,
        "r_spark@skill_eff.json": effects,
        "r_spark_god_type_define@r_spark_god_type_define.json": [{"id": "VITOR", "name": "fate_god_type_define@name@VITOR"}],
        "base_class_define@base_class_define.json": [
            {"id": "striker", "class_name": "base_class_define@class_name@striker"},
            {"id": "vanguard", "class_name": "base_class_define@class_name@knight"},
        ],
        "constant_metagame@constant_meta.json": [{"id": "r_spark_pick_fail_id", "value": "pick_fail_default_r_spark"}],
    }
    db = root / "db"
    db.mkdir()
    for name, content in tables.items():
        (db / name).write_text(json.dumps(content), encoding="utf-8")
    (root / "text" / "en").mkdir(parents=True)
    (root / "text" / "en" / "text.json").write_text(json.dumps([{"id": key, "text": text} for key, text in TEXT.items()]), encoding="utf-8")


@pytest.fixture
def built(tmp_path, monkeypatch) -> tuple[list[dict], list[dict], list]:
    """Both outputs and the issues from a build over the fixture client, with no earlier output on disk."""
    _write_client(tmp_path)
    monkeypatch.setattr(epiphanies, "_existing", lambda path: [])
    result = epiphanies.build(Context(tmp_path))
    return json.loads(result.files[epiphanies.COMMON_PATH]), json.loads(result.files[epiphanies.DIVINE_PATH]), result.issues


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# build()


def test_common_rows_are_filtered_and_x_bucket_folds_into_cost_zero(built):
    common, _, issues = built
    assert [entry["source_key"] for entry in common] == ["c00000", "c00001", "c00004", "pick_fail_default_r_spark"]
    assert [entry["levels"] for entry in common] == [["0"], ["1"], ["4+"], ["0", "1"]]
    assert not issues


def test_common_entry_shape(built):
    entry = built[0][0]
    assert entry == {
        "id": "com_c00000",
        "section": "Other",
        "display_section": "Other",
        "description": "Morale 1.",
        "rarity": "Common",
        "card_types": ["Attack", "Skill"],
        "allowed_classes": ["Striker", "Vanguard"],
        "levels": ["0"],
        "tags": [],
        "source_key": "c00000",
        "raw_text": "Morale 1.\nCOMMON\nAttack\nSkill\nStriker\nVanguard\n0",
    }


def test_divine_entries_use_client_god_names_and_granted_talents(built):
    _, divine, _ = built
    weak, hand = divine
    assert (weak["id"], weak["god"], weak["display_god"], weak["rarity"]) == ("div_add_r_spark_vitor_06", "Vitor", "Vytor", "Unique")
    assert (weak["description"], weak["tags"], weak["levels"]) == ("Always Attack Weakness.", ["Weakness Attack"], [])
    assert hand["description"] == "If 8 or more cards are in hand, change Cost to 0."
    assert hand["levels"] == ["1", "2", "3", "4+"]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Pure helpers


@pytest.mark.parametrize(("cost_min", "cost_max", "expected"), [
    (-1, -1, ["0"]),
    (0, 0, ["0"]),
    (3, 3, ["3"]),
    (4, 99, ["4+"]),
    (-1, 1, ["0", "1"]),
    (1, 99, ["1", "2", "3", "4+"]),
    (-1, 99, []),
    (0, 99, []),
    (99, 99, ["4+"]),
])
def test_level_labels(cost_min, cost_max, expected):
    assert epiphanies.level_labels(cost_min, cost_max) == expected


def test_god_name():
    assert epiphanies.god_name("Diallos's Epiphany", "DIALLOS") == "Diallos"
    assert epiphanies.god_name("Vytor's Epiphany", "VITOR") == "Vytor"
    assert epiphanies.god_name(None, "CALIGO") == "Caligo"


def test_drop_duplicates_keeps_rows_whose_card_filters_differ():
    entry = {"description": "Draw 1.", "levels": ["1"], "source_key": "a"}
    pairs = [
        ({"target_card_include_talent": "[TALENT_EXHAUST]"}, entry),
        ({"target_card_include_talent": "[TALENT_EXHAUST]"}, {**entry, "source_key": "b"}),
        ({"target_card_include_talent": "[]"}, {**entry, "source_key": "c"}),
    ]
    assert [kept["source_key"] for kept in epiphanies.drop_duplicates(pairs)] == ["a", "c"]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# assign_ids()


def _new(source_key: str, description: str, levels: list[str], god: str | None = None) -> dict:
    """A generated entry with the fields `assign_ids()` reads."""
    entry = {"source_key": source_key, "description": description, "card_types": ["Attack"], "allowed_classes": [], "levels": levels}
    if god:
        entry["god"] = god
    return entry


def _old(entry_id: str, description: str, levels: list[str], god: str | None = None, source_key: str = "0123456789ab") -> dict:
    """An entry as the output file holds it. The default `source_key` is a hand-made scraped hash."""
    return {**_new(source_key, description, levels, god), "id": entry_id}


def test_assign_ids_reuses_ids_recorded_by_source_key():
    ids, dropped = epiphanies.assign_ids([_new("c00001", "Morale 1.", ["1"])], [_old("com_0002", "Anything", ["3"], source_key="c00001")], "com_")
    assert (ids, dropped) == ({"c00001": "com_0002"}, [])


def test_assign_ids_matches_hand_made_entries_by_level_and_wording():
    entries = [_new("c00000", "Morale 1.", ["0"]), _new("c00001", "Morale 1.", ["1"]), _new("c09999", "Brand new effect.", ["2"])]
    existing = [_old("com_0001", "Morale 1", ["1", "2", "3", "4+"]), _old("com_0002", "Morale 1", ["1"]), _old("com_0003", "Removed effect", ["2"])]
    ids, dropped = epiphanies.assign_ids(entries, existing, "com_", epiphanies._LEGACY_COMMON_LEVELS)
    assert ids == {"c00000": "com_0001", "c00001": "com_0002", "c09999": "com_c09999"}
    assert dropped == ["com_0003"]


def test_assign_ids_keeps_divine_matches_within_one_god():
    entries = [_new("add_vitor_1", "Defeat: Draw 3.", [], "Vitor"), _new("add_caligo_1", "Defeat: Draw 3.", [], "Caligo")]
    existing = [_old("div_0001", "Destroy: Draw 3", [], "Caligo"), _old("div_0002", "Destroy: Draw 3", [], "Vitor")]
    ids, _ = epiphanies.assign_ids(entries, existing, "div_")
    assert ids == {"add_vitor_1": "div_0002", "add_caligo_1": "div_0001"}


def test_assign_ids_ignores_entries_from_earlier_generated_runs():
    # An entry whose row is gone is not a hand-made one, so its id is not handed to a different row.
    ids, dropped = epiphanies.assign_ids([_new("c00002", "Morale 2.", ["2"])], [_old("com_0003", "Morale 2.", ["2"], source_key="c00099")], "com_")
    assert (ids, dropped) == ({"c00002": "com_c00002"}, [])
