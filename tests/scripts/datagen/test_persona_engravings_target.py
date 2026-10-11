"""
Tests for the `persona_engravings` datagen target, on a tiny fixture client written to a temp folder.

The slot-combination keys and cost modifiers are checked on their own, then a whole build checks the engraving fields,
pinned ids, the Persona card header and its image map.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.datagen import naming
from scripts.datagen.overrides import Overrides
from scripts.datagen.runner import Context
from scripts.datagen.targets import neutral_cards, persona_engravings

SHORT = {"ds_lux": "lux", "ds_umbra": "umbra"}
ORDER = ["ds_lux", "ds_umbra"]

TEXT = {
    "slot@desc@ds_lux_0001": "When a target with an $Action Count$ of <cc>1</> is present,<br>decrease Cost of this card by #result_ev_0#",
    "slot@desc@ds_umbra_0001": "^TRIGGER_EID_UMBRA_AMT_5^ Add #cs_ev_0_0# Hit(s)<br>for each#n_result_vt_mul_1_0# $Umbra Engraving$",
    "slot@name@ds_lux": "Lux",
    "slot@name@ds_umbra": "Umbra",
    "tooltip@title@trigger_eid_umbra_amt_5": "Umbra Engraving 5",
    "tooltip@title@talent_no_count": "Haste",
    "tooltip@title@talent_exhaust_n": "Exhaust",
    "card_atk": "Attack",
    "card_skill": "Skill",
    "card@name@card_test_eid_1": "Persona",
    "base_class_define@class_name@striker": "Striker",
}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _reward(row_id: str, slot_type: str, category: str, effects: str, **extra) -> dict:
    """
    One `eidolon_card_reward` row with only the columns the target reads.

    Args:
        row_id: The row id.
        slot_type: The slot type id, such as "ds_lux".
        category: The `target_card_category` cell.
        effects: The `link_skill_eff_id` cell.
        extra: Any other columns.

    Returns:
        The row.
    """
    row = {
        "id": row_id,
        "desc": f"slot@desc@{row_id}",
        "link_eidolon_slot_type_define_id": slot_type,
        "link_skill_eff_id": effects,
        "slot_add_card_talent": "[]",
        "slot_add_cost": "0",
        "slot_add_cost_mathsign": "MATHSIGN_NONE",
        "target_card_category": category,
        "target_link_base_class_define_id": "[]",
    }
    row.update(extra)
    return row


def _write(path: Path, rows) -> None:
    """Write a JSON fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def _context(root: Path, pinned: dict[str, str]) -> Context:
    """
    A run context over a fixture client.

    Args:
        root: The temp folder to write the client into.
        pinned: legacy engraving id -> client row id.

    Returns:
        The context.
    """
    db = root / "db"
    _write(db / persona_engravings.REWARD_TABLE, [
        _reward("ds_umbra_0001", "ds_umbra", "[CARD_ATK]", "[eff_umbra]"),
        _reward(
            "ds_lux_0001", "ds_lux", "[CARD_ATK]", "[eff_lux]", slot_add_cost="1", slot_add_cost_mathsign="MATHSIGN_ADD",
            slot_add_card_talent="[TALENT_NO_COUNT]", target_link_base_class_define_id="[striker]",
        ),
    ])
    _write(db / "eidolon_card_define@skill_eff.json", [
        {"id": "eff_lux", "eff": "SKILL_EFF_COST", "eff_value": "2"},
        {"id": "eff_umbra", "eff": "SKILL_EFF_ADD_CS", "eff_value": "0", "link_cs_id": "[cs_hits]"},
        {"id": "eff_hits", "eff": "SKILL_EFF_ADD_HIT", "eff_value": "2"},
    ])
    _write(db / "cs(eidolon)@cs.json", [{"id": "cs_hits", "link_skill_eff_id": "[eff_hits]"}])
    _write(db / persona_engravings.SLOT_TYPE_TABLE, [
        {"id": "ds_lux", "name": "slot@name@ds_lux", "slot_type": "LUX"},
        {"id": "ds_umbra", "name": "slot@name@ds_umbra", "slot_type": "UMBRA"},
    ])
    _write(db / persona_engravings.SLOT_INFO_TABLE, [{"id": "eid_1", "link_card_id": "card_test_eid_1"}])
    _write(db / "card(eidolon)@card.json", [{"id": "card_test_eid_1", "name": "card@name@card_test_eid_1"}])
    _write(db / persona_engravings.ILLUSTRATION_TABLE, [
        {"id": f"{a}_{b}{suffix}", "card_category": category, "change_to_sct_name": f"art_{a}_{b}{suffix}", "slot_type_0": a, "slot_type_1": b}
        for category, suffix in (("CARD_ATK", ""), ("CARD_SKILL", "_ski"))
        for a, b in (("ds_umbra", "ds_umbra"), ("ds_lux", "none"), ("ds_umbra", "ds_lux"), ("ds_umbra", "none"), ("ds_lux", "ds_lux"))
    ])
    _write(db / "base_class_define@base_class_define.json", [{"id": "striker", "class_name": "base_class_define@class_name@striker"}])
    _write(root / "text" / "en" / "text.json", [{"id": key, "text": text} for key, text in TEXT.items()])
    ctx = Context(root)
    ctx._overrides[persona_engravings.NAME] = Overrides(persona_engravings.NAME, directives={naming.IDS_KEY: pinned})
    ctx._overrides[neutral_cards.NAME] = Overrides(neutral_cards.NAME, directives={naming.IDS_KEY: {"n_0081": "card_test_eid_1"}})
    return ctx


def _built(ctx: Context):
    """
    Run the target and read its output back.

    Args:
        ctx: The run context.

    Returns:
        The single Persona card and the issue messages.
    """
    result = persona_engravings.build(ctx)
    return json.loads(result.files[persona_engravings.OUTPUT_PATH])[0], [issue.message for issue in result.issues]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Combination keys


def test_combination_key_one_slot():
    assert persona_engravings.combination_key("ds_lux", "none", SHORT, ORDER) == "half_lux"


def test_combination_key_same_type_twice():
    assert persona_engravings.combination_key("ds_umbra", "ds_umbra", SHORT, ORDER) == "all_umbra"


def test_combination_key_mixed_is_order_independent():
    assert persona_engravings.combination_key("ds_umbra", "ds_lux", SHORT, ORDER) == "lux_and_umbra"
    assert persona_engravings.combination_key("ds_lux", "ds_umbra", SHORT, ORDER) == "lux_and_umbra"


def test_combination_key_unknown_type():
    assert persona_engravings.combination_key("ds_other", "none", SHORT, ORDER) is None


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Whole build


def test_build_maps_engraving_fields(tmp_path):
    card, issues = _built(_context(tmp_path, {"pe_0001": "ds_lux_0001"}))
    assert card["engravings"][0] == {
        "engraving_id": "pe_0001",
        "eidolon": "Lux",
        "card_type": "Attack",
        "modifiers": ["Cost +1", "Haste"],
        "allowed_classes": ["Striker"],
        "tags": [],
        "description": "When a target with an Action Count of 1 is present, decrease Cost of this card by 2",
    }
    assert issues == []


def test_build_resolves_status_values_triggers_and_drops_battle_counts(tmp_path):
    card, _ = _built(_context(tmp_path, {}))
    umbra = next(item for item in card["engravings"] if item["engraving_id"] == "ds_umbra_0001")
    assert umbra["description"] == "Umbra Engraving 5: Add 2 Hit(s) for each Umbra Engraving"
    assert umbra["modifiers"] == []


def test_build_puts_pinned_ids_first_and_new_ones_after(tmp_path):
    card, _ = _built(_context(tmp_path, {"pe_0001": "ds_umbra_0001"}))
    assert [item["engraving_id"] for item in card["engravings"]] == ["pe_0001", "ds_lux_0001"]


def test_build_reports_a_pinned_id_missing_from_the_client(tmp_path):
    _, issues = _built(_context(tmp_path, {"pe_0099": "ds_gone"}))
    assert "persona_engravings: pinned id pe_0099 points at ds_gone, which is not a kept engraving in the client" in issues


def test_build_card_header_and_image_map(tmp_path):
    card, _ = _built(_context(tmp_path, {}))
    header = {key: value for key, value in card.items() if key != "engravings"}
    assert header == {
        "id": "n_0081",
        "image_id": "n_0081",
        "name": "Persona",
        "category": "persona",
        "image_type": "persona",
        "image_path": "persona/lux.webp",
        "persona_image_paths": {
            "lux": "persona/lux.webp",
            "umbra": "persona/umbra.webp",
            "half_lux": "persona/half_lux.webp",
            "half_umbra": "persona/half_umbra.webp",
            "all_lux": "persona/all_lux.webp",
            "lux_and_umbra": "persona/lux_and_umbra.webp",
            "all_umbra": "persona/all_umbra.webp",
        },
    }
