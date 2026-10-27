"""
Tests for the `neutral_cards` datagen target, on a tiny fixture client written to a temp folder.

The text repairs and small helpers are checked on their own, then a whole build checks the row selection, pinned ids,
tags, class restrictions and which card art gets added.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from scripts.datagen import naming
from scripts.datagen.overrides import Overrides
from scripts.datagen.runner import Context
from scripts.datagen.targets import neutral_cards

TEXT = {
    "card@name@card_test_ne_1": "Heavy Bash",
    "card@desc@card_test_ne_1": "#result_coeff_ev_0# Damage<br>#result_ev_1# $Vulnerable$",
    "card@name@card_test_ta_1": "Forbidden: Engraved Malice",
    "card@desc@card_test_ta_1": "$Draw$ #result_ev_0#",
    "card@name@card_test_enc_1": "Old Sword",
    "card@desc@card_test_enc_1": "For each Attack Card Drawn,<br>#result_ev_0#%% Coordinated Attack",
    "card@name@card_test_enc_2": "Mutate",
    "card@desc@card_test_enc_2": "A curse",
    "card@name@card_test_ab_1": "Blissful Oblivion",
    "card@desc@card_test_ab_1": "Another curse",
    "card@name@card_test_mon_1": "Shy Gardener",
    "card@desc@card_test_mon_1": "#result_coeff_ev_0# Damage",
    "card@name@card_test_mon_1_opt1": "Shy Gardener",
    "card@desc@card_test_mon_1_opt1": "#result_coeff_ev_0# Damage",
    "card_atk": "Attack",
    "card_skill": "Skill",
    "card_curse": "Curse",
    "tooltip@title@talent_exhaust": "Exhaust",
    "base_class_define@class_name@striker": "Striker",
    "base_class_define@class_name@knight": "Vanguard",
}

EFFECTS = [
    {"id": "eff_dmg", "eff": "SKILL_EFF_DMG", "eff_attr": "[]", "eff_value": "200"},
    {"id": "eff_two", "eff": "SKILL_EFF_ADD_CS", "eff_attr": "[]", "eff_value": "2"},
]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _card(card_id: str, sort: str, category: str = "CARD_ATK", classes: str = "[]", effects: str = "[eff_dmg,eff_two]", **extra) -> dict:
    """
    One card row with only the columns the target reads.

    Args:
        card_id: The row id.
        sort: Such as "SORT_NEUTRAL".
        category: Such as "CARD_SKILL".
        classes: The `ownable_link_base_class_define_id` cell.
        effects: The `link_skill_eff_id` cell.
        extra: Any other columns, such as `talent` or `link_extra_tag_id`.

    Returns:
        The row.
    """
    row = {
        "id": card_id,
        "sort": sort,
        "card_category": category,
        "cost": "1",
        "name": f"card@name@{card_id}",
        "desc": f"card@desc@{card_id}",
        "link_skill_eff_id": effects,
        "ownable_link_base_class_define_id": classes,
        "talent": "[TALENT_NONE]",
        "link_extra_tag_id": "[]",
        "sct_name": f"art_{card_id}",
    }
    row.update(extra)
    return row


def _write(path: Path, rows) -> None:
    """Write a JSON fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def _context(root: Path, overrides: Overrides) -> Context:
    """
    A run context over a fixture client.

    Args:
        root: The temp folder to write the client into.
        overrides: The `neutral_cards` overrides to use instead of the real file.

    Returns:
        The context.
    """
    db = root / "db"
    _write(db / "card(public)@card.json", [_card("card_test_ne_1", "SORT_NEUTRAL", classes="[striker,vanguard]", talent="[TALENT_EXHAUST]")])
    _write(db / "card(disaster)@card.json", [_card("card_test_ta_1", "SORT_TABOO", "CARD_SKILL", effects="[eff_two]", link_extra_tag_id="[ds01]")])
    _write(db / "card(encounter)@card.json", [
        _card("card_test_enc_1", "SORT_ETC", "CARD_SKILL", effects="[eff_two]", link_extra_tag_id="[ds02_ban]"),
        _card("card_test_enc_2", "SORT_NEGATIVE", "CARD_CURSE"),
    ])
    _write(db / "card(etc)@card.json", [_card("card_test_ab_1", "SORT_NEGATIVE", "CARD_CURSE")])
    _write(db / "card(monster)@card.json", [
        _card("card_test_mon_1", "SORT_MONSTER_UNIQUE"),
        _card("card_test_mon_1_opt1", "SORT_MONSTER_UNIQUE"),
    ])
    _write(db / "card(public)@skill_eff.json", EFFECTS)
    _write(db / "base_class_define@base_class_define.json", [
        {"id": "striker", "class_name": "base_class_define@class_name@striker"},
        {"id": "vanguard", "class_name": "base_class_define@class_name@knight"},
    ])
    _write(db / "extra_tag@extra_tag.json", [
        {"id": "ds01", "type": "DISASTER_SEASON"},
        {"id": "ds02_ban", "type": "DISASTER_SEASON_BAN"},
    ])
    _write(root / "text" / "en" / "text.json", [{"id": key, "text": text} for key, text in TEXT.items()])
    art = root / "card_illustration"
    art.mkdir()
    Image.new("RGBA", (42, 63), (200, 30, 30, 255)).save(art / "art_card_test_ne_1.png")
    ctx = Context(root)
    ctx._overrides[neutral_cards.NAME] = overrides
    return ctx


def _overrides(pinned: dict[str, str] | None = None, **fields) -> Overrides:
    """
    `neutral_cards` overrides like the real file: the opt rows excluded and some ids pinned.

    Args:
        pinned: legacy output id -> client card id.
        fields: Extra override entries, keyed by output id.

    Returns:
        The overrides.
    """
    return Overrides(neutral_cards.NAME, entries=fields, exclude=["card_*_opt*"], directives={naming.IDS_KEY: pinned or {}})


def _built(ctx: Context):
    """
    Run the target and read its output back.

    Args:
        ctx: The run context.

    Returns:
        The cards by id, the result, and the issue messages.
    """
    result = neutral_cards.build(ctx)
    cards = json.loads(result.files[neutral_cards.OUTPUT_PATH])
    return {card["id"]: card for card in cards}, result, [issue.message for issue in result.issues]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Small helpers


def test_restrictions_line():
    assert neutral_cards.restrictions([]) == "No Class restrictions"
    assert neutral_cards.restrictions(["Ranger", "Hunter"]) == "Ranger, Hunter only"


def test_legacy_ids_maps_client_ids_to_pinned_ids():
    overrides = _overrides({"n_0001": "card_a", "m_0001": "card_b"})
    assert naming.legacy_ids(overrides) == {"card_a": "n_0001", "card_b": "m_0001"}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Whole build


def test_build_selects_rows_by_sort_and_keeps_pinned_cards(tmp_path):
    cards, _, issues = _built(_context(tmp_path, _overrides({"n_0013": "card_test_ab_1"})))
    # The encounter curse is not a SORT_ETC row, the opt row is excluded, and the etc curse is kept only because it is pinned.
    assert sorted(cards) == ["card_test_enc_1", "card_test_mon_1", "card_test_ne_1", "card_test_ta_1", "n_0013"]
    assert not any("pinned" in issue or "unresolved" in issue for issue in issues)


def test_build_maps_fields(tmp_path):
    cards, _, _ = _built(_context(tmp_path, _overrides({"n_0001": "card_test_ne_1"})))
    assert cards["n_0001"] == {
        "id": "n_0001",
        "name": "Heavy Bash",
        "cost": 1,
        "card_type": "Attack",
        "category": "neutral",
        "tags": ["neutral"],
        "effect_tags": ["Exhaust"],
        "description": "[Exhaust] 200% Damage. 2 Vulnerable.",
        "restrictions": "Striker, Vanguard only",
        "allowed_classes": ["Striker", "Vanguard"],
        "image_path": "neutral-cards/neutral/n_0001.webp",
    }


def test_build_tags_season_and_forbidden_cards(tmp_path):
    cards, _, _ = _built(_context(tmp_path, _overrides()))
    assert cards["card_test_ta_1"]["tags"] == ["neutral", "season", "forbidden"]
    # A season ban tag is not a season card.
    assert cards["card_test_enc_1"]["tags"] == ["neutral"]


def test_build_repairs_wrapped_text(tmp_path):
    cards, _, _ = _built(_context(tmp_path, _overrides()))
    assert cards["card_test_enc_1"]["description"] == "For each Attack Card Drawn, 2% Coordinated Attack."


def test_build_gives_monsters_no_restriction_line(tmp_path):
    cards, _, _ = _built(_context(tmp_path, _overrides()))
    monster = cards["card_test_mon_1"]
    assert (monster["category"], monster["restrictions"], monster["image_path"]) == ("monster", None, "neutral-cards/monster/card_test_mon_1.webp")


def test_build_orders_neutral_before_monster_then_by_name(tmp_path):
    result = neutral_cards.build(_context(tmp_path, _overrides()))
    names = [card["name"] for card in json.loads(result.files[neutral_cards.OUTPUT_PATH])]
    assert names == ["Forbidden: Engraved Malice", "Heavy Bash", "Old Sword", "Shy Gardener"]


def test_build_adds_missing_art_and_reports_art_it_cannot_find(tmp_path):
    _, result, issues = _built(_context(tmp_path, _overrides()))
    added = neutral_cards.DATA_DIR / "neutral-cards" / "neutral" / "card_test_ne_1.webp"
    assert list(result.new_files) == [added]
    # Art keeps the client illustration's own size.
    assert Image.open(io.BytesIO(result.new_files[added])).size == (42, 63)
    assert "neutral_cards: no illustration in the client for card_test_mon_1 (art_card_test_mon_1.png)" in issues


def test_build_reports_a_pinned_id_missing_from_the_client(tmp_path):
    _, _, issues = _built(_context(tmp_path, _overrides({"n_0099": "card_gone"})))
    assert "neutral_cards: pinned id n_0099 points at card_gone, which is not a kept card in the client" in issues


def test_build_applies_field_overrides(tmp_path):
    overrides = _overrides({"n_0001": "card_test_ne_1"}, n_0001={"name": "Heavier Bash", "_why": "test"})
    cards, _, issues = _built(_context(tmp_path, overrides))
    assert cards["n_0001"]["name"] == "Heavier Bash"
    assert not any("n_0001" in issue for issue in issues)
