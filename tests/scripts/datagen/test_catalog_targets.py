"""
Tests for the `monster_catalog` and `eff_type_catalog` datagen targets.

Both wrap an older build script. The monster catalog is built from a tiny fixture client written to a temp folder, to
check the script now reads the client it is given. The eff catalog refresh is checked on inline data, to pin which
fields are regenerated and which are kept.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import build_monster_catalog
from scripts.datagen.runner import Context
from scripts.datagen.targets import eff_type_catalog, monster_catalog

# The client writes some apostrophes curly. Built with chr() to keep this file plain ASCII.
CURLY_APOSTROPHE = chr(0x2019)

MONSTERS = [
    {"id": "1001001_01", "name": "monster@name@1001001_01", "stat_def_pct": "100", "faction_ego": "RED", "grade": "GRADE_NORMAL"},
    {"id": "1001002_02", "name": "monster@name@1001002_02", "stat_def_pct": "200", "faction_ego": "EGO_NONE", "grade": "GRADE_NORMAL"},
    {"id": "1001003_01", "name": "monster@name@1001003_01", "stat_def_pct": "100", "faction_ego": "none", "grade": "GRADE_INTERACTIVE_PROP"},
]

MONSTER_TEXT = {
    "monster@name@1001001_01": "Zed",
    "monster@name@1001002_02": f"Pharanes{CURLY_APOSTROPHE}s Fragment",
    "monster@name@1001003_01": "Barrel",
}

HAND_FIELDS = {
    "category": "damage",
    "confidence": "verified",
    "effect": {"formula_ref": "F_DMG", "kind": "damage"},
    "notes": "Hand-written.",
    "stack_rule": "instant",
    "target_resolution": "selected_unit",
    "todos": [],
    "trigger": "on_skill_use",
}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _write_client(root: Path) -> None:
    """
    Write a fixture client with two stat tiers and three monsters, one of them a prop.

    Args:
        root: The folder to write `db/` and `text/` into.
    """
    db = root / "db"
    db.mkdir()
    (db / "tier_monster_stat@tier_monster_stat.json").write_text(json.dumps([
        {"id": "1", "stage_enter_link_mon_stat_id": "stat_1"},
        {"id": "2", "stage_enter_link_mon_stat_id": "stat_2"},
    ]), encoding="utf-8")
    (db / "mon_stat@mon_stat.json").write_text(json.dumps([{"id": "stat_1", "stat_def": "47"}, {"id": "stat_2", "stat_def": "49"}]), encoding="utf-8")
    (db / "monster(test)@monster.json").write_text(json.dumps(MONSTERS), encoding="utf-8")
    text = root / "text" / "en"
    text.mkdir(parents=True)
    (text / "text.json").write_text(json.dumps([{"id": key, "text": value} for key, value in MONSTER_TEXT.items()]), encoding="utf-8")


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# monster_catalog


def test_build_catalog_reads_the_given_client(tmp_path):
    _write_client(tmp_path)
    catalog, counts = build_monster_catalog.build_catalog(tmp_path)
    assert catalog == [
        {"id": "1001001_01", "name": "Zed", "def": 47, "has_weak": True},
        {"id": "1001002_02", "name": f"Pharanes{CURLY_APOSTROPHE}s Fragment", "def": 98, "has_weak": False},
    ]
    assert counts == {"skipped_no_id": 0, "skipped_dup": 0, "tier_miss": 0}


def test_target_cleans_names_and_reports_the_id_delta(tmp_path):
    _write_client(tmp_path)
    result = monster_catalog.build(Context(tmp_path))
    written = json.loads(result.files[monster_catalog.CATALOG_PATH])
    assert [entry["name"] for entry in written] == ["Zed", "Pharanes's Fragment"]
    assert result.issues == []


def test_summarise_counts_added_and_removed_ids():
    catalog = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert monster_catalog.summarise(catalog, {"a", "z"}) == "3 monsters (+2, -1)"


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# eff_type_catalog


def test_refresh_updates_client_fields_and_keeps_the_rest():
    existing = {
        "SKILL_EFF_DMG": {**HAND_FIELDS, "observed_count": 1234, "client_instances": 1, "params_used": [], "linked_conditions": ["old"], "linked_cs_ids": []},
        "SKILL_EFF_GONE": {**HAND_FIELDS, "observed_count": 5, "client_instances": 1, "params_used": [], "linked_conditions": [], "linked_cs_ids": []},
    }
    by_type = {
        "SKILL_EFF_DMG": [
            {"id": "e1", "eff": "SKILL_EFF_DMG", "eff_value": "100", "eff_link_condition_id": "cd_a", "link_cs_id": "[cs01, cs02]"},
            {"id": "e2", "eff": "SKILL_EFF_DMG", "eff_value": "150", "eff_link_condition_id": "none", "link_cs_id": "[]"},
        ],
        "SKILL_EFF_NEW": [{"id": "e3", "eff": "SKILL_EFF_NEW"}],
    }
    catalog, gone = eff_type_catalog.refresh(existing, by_type)
    assert gone == ["SKILL_EFF_GONE"]
    assert list(catalog) == ["SKILL_EFF_DMG"]
    entry = catalog["SKILL_EFF_DMG"]
    assert entry["client_instances"] == 2
    assert entry["params_used"] == ["eff_link_condition_id", "eff_value", "id", "link_cs_id"]
    assert entry["linked_conditions"] == ["cd_a"]
    assert entry["linked_cs_ids"] == ["cs01", "cs02"]
    assert entry["observed_count"] == 1234
    assert {key: entry[key] for key in HAND_FIELDS} == HAND_FIELDS
