"""
Tests for the `encyclopedia_cards` datagen target, on a tiny fixture client written to a temp folder.

The fixture has one card from each of the game's card archive groups, so a single build checks grouping, epiphanies, the
Season 5 cards that live outside the `card(*)` shards, and which art is reused or added.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from scripts.datagen.overrides import Overrides
from scripts.datagen.runner import Context
from scripts.datagen.targets import encyclopedia_cards, neutral_cards
from tests.scripts.datagen.fixture_client import write_client

# Nia is a shipped combatant whose deck builder art lives in the `nia` folder.
NIA = 1003

TEXT = {
    "card@name@c_1003_srt1": "Strike",
    "card@desc@c_1003_srt1": "#result_coeff_ev_0# Damage",
    "card@name@c_1003_srt1_rsp1": "Strike",
    "card@desc@c_1003_srt1_rsp1": "#result_coeff_ev_0# Damage, twice",
    "card@name@c_1003_uni1": "G Chord",
    "card@desc@c_1003_uni1": "Gain $Spore Propagation#1$ and $Wave$<br>Create <cc><u>Contaminated Spore</u></> and <cc><u>Echo</u></>",
    "card@name@c_1003_eps": "Finale",
    "card@desc@c_1003_eps": "^TRIGGER_EXHAUST^ Draw 2, $Fixed Heal$, $activate$ Agony<br>Create ^card@card_ab_2^, <cc><u>Heavy Bash</u></>, <u>Futility</u>, "
    "<u>Softie★</u> and <u>Anchor Shots</u>",
    "card@name@card_ne_1": "Heavy Bash",
    "card@desc@card_ne_1": "#result_coeff_ev_0# Damage",
    "card@name@card_mon_1": "Shy Gardener",
    "card@desc@card_mon_1": "When this card is $Drawn$, start a $Quest$",
    "card@name@card_ds05_a_1": "Memory: Suppression",
    "card@desc@card_ds05_a_1": "#result_coeff_ev_0# Damage to all enemies",
    "card@name@card_ab_1": "Bleed",
    "card@desc@card_ab_1": "Unplayable",
    "card@name@card_ds02_9": "Contaminated Spore",
    "card@desc@card_ds02_9": "Lose 1 Health",
    "card@name@card_ab_2": "Horrifying Memory",
    "card@desc@card_ab_2": "Unplayable",
    "card@name@c_2001_cre1": "Echo",
    "card@name@card_mon_2": "Echo",
    "card@name@c_1003_cre1": "Futility",
    "card@name@card_ab_3": "Futility",
    "card@name@c_1003_cre2": "Softie ★",
    "card@name@c_1003_cre3": "Anchor Shot",
    "tooltip@title@card_fixedcure": "Fixed Healing",
    "tooltip@desc@card_fixedcure": "Heal that ignores healing effects",
    "tooltip@title@card_activate": "Activate",
    "tooltip@desc@card_activate": "Using or proccing a card",
    "tooltip@title@t_spore": "Spore Propagation",
    "tooltip@desc@t_spore": "For #tv# turn(s), spread <cc>1</> spore<br>#synergy_ds04_01#",
    "tooltip@title@t_wave": "Wave",
    "tooltip@title@trigger_exhaust": "Incinerate:",
    "tooltip@desc@trigger_exhaust": "When this card is $Exhaust$ed, activate effect",
    "tooltip@title@talent_ignite": "Ignition",
    "tooltip@desc@talent_ignite": "If a card is Exhausted, decrease Cost of this card by <cc>1</>",
    "tooltip@title@talent_exhaust": "Exhaust",
    "tooltip@desc@talent_exhaust": "When this card is activated, move to Exhaust Pile",
    "card_atk": "Attack",
    "card_skill": "Skill",
    "card_power": "Power",
    "card_curse": "Curse",
    "tooltip@title@talent_unplayable": "Unplayable",
    "tooltip@title@card_draw": "Draw",
    "tooltip@desc@card_draw": "Move a card from $Draw Pile$ to hand",
    "archive_card@title@public_striker": "Striker",
    "archive_card@title@monster_nihilum": "Nihilum Faction",
    "archive_card@title@season_s5": "A Promise Upon the Snow",
    "archive_card@title@etc_abnorm": "Status Ailment",
}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _card(card_id: str, category: str = "CARD_ATK", **extra) -> dict:
    """
    One card row with only the columns the target reads.

    Args:
        card_id: The row id.
        category: Such as "CARD_SKILL".
        extra: Any other columns, such as `sort` or `cost`.

    Returns:
        The row.
    """
    row = {
        "id": card_id,
        "sort": "SORT_NEUTRAL",
        "card_category": category,
        "cost": "1",
        "name": f"card@name@{card_id}",
        "desc": f"card@desc@{card_id}",
        "link_skill_eff_id": "[eff_dmg]",
        "ownable_link_base_class_define_id": "[]",
        "talent": "[TALENT_NONE]",
        "link_extra_tag_id": "[]",
        "sct_name": f"art_{card_id}",
    }
    row.update(extra)
    return row


def _archive(card_id: str, sub_categories: str, sort_type: str = "none", order: int = 1) -> dict:
    """
    One card archive row.

    Args:
        card_id: The card it lists.
        sub_categories: The `link_archive_card_sub_category_id` cell, such as "[season_s5]".
        sort_type: Such as "season_power".
        order: The row's order within its table.

    Returns:
        The row.
    """
    return {
        "id": f"archive_{card_id}",
        "link_card_id": card_id,
        "link_archive_card_sub_category_id": sub_categories,
        "link_archive_card_sort_type_id": sort_type,
        "order": str(order),
    }


def _context(root: Path) -> Context:
    """
    A run context over a fixture client.

    Args:
        root: The temp folder to write the client into.

    Returns:
        The context, with the public card pinned to the legacy deck builder id `n_0001` and two hand-mapped keywords.
    """
    write_client(root, {
        "card(ikarus)@card.json": [
            _card("c_1003_srt1"),
            _card("c_1003_srt1_rsp1"),
            _card("c_1003_uni1", "CARD_SKILL", cost="-1"),
            _card("c_1003_eps", "CARD_SKILL", talent="[TALENT_IGNITE,TALENT_EXHAUST_2]"),
            _card("c_1003_col", "CARD_SKILL"),
            _card("c_2001_cre1"),
            _card("c_1003_cre1"),
            _card("c_1003_cre2"),
            _card("c_1003_cre3"),
        ],
        "card(public)@card.json": [_card("card_ne_1")],
        "card(season)@card.json": [_card("card_ds02_9", "CARD_CURSE", cost="0")],
        "card(monster)@card.json": [_card("card_mon_1", "CARD_SKILL", sort="SORT_MONSTER_UNIQUE", rarity="RARITY_RARE"), _card("card_mon_2")],
        "card(etc)@card.json": [
            _card("card_ab_1", "CARD_CURSE", sort="SORT_NEGATIVE", desc="none", talent="[TALENT_UNPLAYABLE]"),
            _card("card_ab_2", "CARD_CURSE", sort="SORT_NEGATIVE"),
            _card("card_ab_3", "CARD_CURSE", sort="SORT_NEGATIVE"),
        ],
        "tooltip@tooltip.json": [
            {"id": "T_SPORE", "title": "tooltip@title@t_spore", "desc": "tooltip@desc@t_spore", "link_cs_id": "none"},
            {"id": "T_WAVE", "title": "tooltip@title@t_wave", "desc": "none", "link_cs_id": "none"},
            {"id": "TRIGGER_EXHAUST", "title": "tooltip@title@trigger_exhaust", "desc": "tooltip@desc@trigger_exhaust", "link_cs_id": "none"},
            {"id": "TALENT_IGNITE", "title": "tooltip@title@talent_ignite", "desc": "tooltip@desc@talent_ignite", "link_cs_id": "none"},
            {"id": "TALENT_EXHAUST", "title": "tooltip@title@talent_exhaust", "desc": "tooltip@desc@talent_exhaust", "link_cs_id": "none"},
            {"id": "CARD_FIXEDCURE", "title": "tooltip@title@card_fixedcure", "desc": "tooltip@desc@card_fixedcure", "link_cs_id": "none"},
            {"id": "CARD_ACTIVATE", "title": "tooltip@title@card_activate", "desc": "tooltip@desc@card_activate", "link_cs_id": "none"},
            {"id": "CARD_DRAW", "title": "tooltip@title@card_draw", "desc": "tooltip@desc@card_draw", "link_cs_id": "none"},
        ],
        "memory_grade_define@card.json": [_card("card_ds05_a_1", "CARD_POWER", cost="0")],
        "card(public)@skill_eff.json": [{"id": "eff_dmg", "eff": "SKILL_EFF_DMG", "eff_attr": "[]", "eff_value": "200"}],
        "card(ikarus)@card_r_spark.json": [{"id": "rsp1_c_1003_srt1", "link_card_id": "c_1003_srt1", "change_link_card_id": "c_1003_srt1_rsp1"}],
        "char_base@char_combatant.json": [{"id": str(NIA), "collapse_skill_link_card_id": "c_1003_eps"}],
        "archive_card(combatant)@archive_card.json": [
            _archive("c_1003_srt1", "combatant_start", order=1),
            _archive("c_1003_uni1", "combatant_start", order=2),
            _archive("c_1003_srt1_rsp1", "combatant_uni_spark", order=3),
        ],
        "archive_card(public)@archive_card.json": [_archive("card_ne_1", "[public_all,public_striker]")],
        "archive_card(monster)@archive_card.json": [_archive("card_mon_1", "[monster_nihilum]")],
        "archive_card(season)@archive_card.json": [_archive("card_ds05_a_1", "[season_s5]", "season_power"), _archive("card_ds05_gone", "[season_s5]")],
        "archive_card(etc)@archive_card.json": [_archive("card_ab_1", "[etc_abnorm]")],
    }, TEXT)
    art = root / "card_illustration"
    art.mkdir()
    for name in ("art_card_ds05_a_1", "art_card_ab_1"):
        Image.new("RGBA", (42, 63), (200, 30, 30, 255)).save(art / f"{name}.png")
    ctx = Context(root)
    ctx._overrides[neutral_cards.NAME] = Overrides(neutral_cards.NAME, directives={"_ids": {"n_0001": "card_ne_1"}})
    ctx._overrides[encyclopedia_cards.NAME] = Overrides(encyclopedia_cards.NAME, {
        "Drawn": {"tooltip": "CARD_DRAW", "_why": "Draw's own tooltip"},
        "Quest": {"definition": "One of Cassius' challenges.", "_why": "no tooltip defines it"},
    })
    return ctx


def _built(ctx: Context):
    """
    Run the target and read its output back.

    Args:
        ctx: The run context.

    Returns:
        The output document, its cards by id, the result, and the issue messages.
    """
    result = encyclopedia_cards.build(ctx)
    document = json.loads(result.files[encyclopedia_cards.OUTPUT_PATH])
    return document, {card["id"]: card for card in document["cards"]}, result, [issue.message for issue in result.issues]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Whole build


def test_lists_one_entry_per_archive_card_and_skips_the_rest(tmp_path):
    _, cards, _, issues = _built(_context(tmp_path))
    # Epiphanies fold into their base card, the ego skill is added, the collapse card is not in the archive.
    assert list(cards) == ["c_1003_srt1", "c_1003_uni1", "c_1003_eps", "card_ne_1", "card_ds05_a_1", "card_mon_1", "card_ab_1"]
    assert any("card_ds05_gone" in issue for issue in issues)


def test_combatant_cards_carry_their_character_and_epiphanies(tmp_path):
    _, cards, _, _ = _built(_context(tmp_path))
    strike = cards["c_1003_srt1"]
    assert strike["group"] == "combatant"
    assert strike["kind"] == "starting"
    assert strike["character_id"] == NIA
    assert strike["description"] == "200% Damage."
    assert strike["image"] == "deck-builder/data/combatants/nia/c_1003_srt1.webp"
    assert strike["epiphanies"] == [{"level": 1, "name": "Strike I", "cost": 1, "description": "200% Damage, twice."}]
    assert cards["c_1003_uni1"]["kind"] == "epiphany"
    assert cards["c_1003_uni1"]["cost"] == -1
    assert cards["c_1003_eps"]["kind"] == "ego"


def test_season_five_cards_come_from_their_own_shard(tmp_path):
    document, cards, _, _ = _built(_context(tmp_path))
    memory = cards["card_ds05_a_1"]
    assert (memory["group"], memory["kind"], memory["season"]) == ("season", "power", 5)
    assert memory["card_type"] == "Power"
    assert memory["description"] == "200% Damage to all enemies."
    assert document["seasons"] == [{"number": 5, "title": "A Promise Upon the Snow"}]


def test_labels_and_groups_for_the_shared_cards(tmp_path):
    document, cards, _, _ = _built(_context(tmp_path))
    assert (cards["card_ne_1"]["group"], cards["card_ne_1"]["classes"]) == ("neutral", ["Striker"])
    assert (cards["card_mon_1"]["group"], cards["card_mon_1"]["faction"]) == ("monster", "Nihilum Faction")
    assert cards["card_ab_1"]["group"] == "ailment"
    # Wound has no text, only its traits.
    assert cards["card_ab_1"]["description"] == "[Unplayable]"
    assert document["characters"] == [{"id": NIA, "name": "Nia"}]


def test_reuses_deck_builder_art_and_adds_the_rest(tmp_path):
    _, cards, result, _ = _built(_context(tmp_path))
    assert cards["card_ne_1"]["image"] == "deck-builder/data/neutral-cards/neutral/n_0001.webp"
    assert cards["card_ds05_a_1"]["image"] == "encyclopedia/data/card-art/art_card_ds05_a_1.webp"
    added = {path.as_posix() for path in result.new_files}
    assert added == {"src/pages/encyclopedia/data/card-art/art_card_ds05_a_1.webp", "src/pages/encyclopedia/data/card-art/art_card_ab_1.webp"}
    # Added art keeps the client illustration's own size.
    assert {Image.open(io.BytesIO(data)).size for data in result.new_files.values()} == {(42, 63)}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Keywords and card links


def test_collects_the_keywords_the_card_text_marks_with_their_definitions(tmp_path):
    document, _, _, _ = _built(_context(tmp_path))
    # Marked keywords, triggers (which keep their colon) and traits. Wave has no definition, so it is left out.
    # Battle-only values read X, and lines that are only such a value are dropped. Fixed Heal is a near miss of the
    # tooltip title "Fixed Healing", which the game matches by its Korean text instead. Lower-case keywords such as
    # "activate" are verbs whose sense shifts, so they are left out. Drawn and Quest come from the overrides.
    assert document["keywords"] == [
        {"name": "Drawn", "definition": "Move a card from Draw Pile to hand."},
        {"name": "Exhaust", "definition": "When this card is activated, move to Exhaust Pile."},
        {"name": "Fixed Heal", "definition": "Heal that ignores healing effects."},
        {"name": "Ignition", "definition": "If a card is Exhausted, decrease Cost of this card by 1."},
        {"name": "Incinerate:", "definition": "When this card is Exhausted, activate effect."},
        {"name": "Quest", "definition": "One of Cassius' challenges."},
        {"name": "Spore Propagation", "definition": "For X turn(s), spread 1 spore."},
    ]


def test_reports_keyword_overrides_that_point_nowhere(tmp_path):
    ctx = _context(tmp_path)
    ctx._overrides[encyclopedia_cards.NAME] = Overrides(encyclopedia_cards.NAME, {
        "Drawn": {"tooltip": "CARD_GONE", "_why": "a tooltip the client lost"},
        "Never Marked": {"definition": "Unused.", "_why": "a keyword no card text marks"},
    })
    _, _, _, issues = _built(ctx)
    assert "encyclopedia_cards: keyword override 'Drawn' names tooltip CARD_GONE, which the client lacks" in issues
    assert "encyclopedia_cards: keyword override 'Never Marked' matches no keyword the card text marks" in issues


def test_links_the_cards_the_card_text_names(tmp_path):
    document, _, _, _ = _built(_context(tmp_path))
    # Echo names cards of two families, neither of them the referring card's, so it is not linked. Futility also names two
    # families, but one is the referring card's own. Softie★ drops the name's space, and Anchor Shots is a plural.
    assert document["card_links"] == [
        {"name": "Anchor Shots", "id": "c_1003_cre3"},
        {"name": "Contaminated Spore", "id": "card_ds02_9"},
        {"name": "Futility", "id": "c_1003_cre1"},
        {"name": "Heavy Bash", "id": "card_ne_1"},
        {"name": "Horrifying Memory", "id": "card_ab_2"},
        {"name": "Softie★", "id": "c_1003_cre2"},
    ]


def test_named_cards_missing_from_the_list_are_carried_for_their_preview(tmp_path):
    document, _, _, _ = _built(_context(tmp_path))
    linked = {card["id"]: card for card in document["linked_cards"]}
    assert set(linked) == {"card_ds02_9", "card_ab_2", "c_1003_cre1", "c_1003_cre2", "c_1003_cre3"}
    assert linked["card_ds02_9"] == {
        "id": "card_ds02_9",
        "name": "Contaminated Spore",
        "cost": 0,
        "card_type": "Curse",
        "description": "Lose 1 Health.",
        "image": None,
    }
