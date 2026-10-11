"""
Tests for the shared template resolver, on a fixture client holding the real rows of five cards whose text was checked by
hand against the game, plus a few synthetic rows for the rarer placeholders.
"""

from __future__ import annotations

import pytest

from scripts.datagen.client import Client
from scripts.datagen.templates import TemplateResolver, format_number
from tests.scripts.datagen.fixture_client import write_client


def _card(card_id: str, effects: list[str], talent: str = "[]") -> dict:
    return {"id": card_id, "desc": f"card@desc@{card_id}", "name": f"card@name@{card_id}", "link_skill_eff_id": "[" + ",".join(effects) + "]", "talent": talent}


def _eff(eff_id: str, kind: str, value: str, **extra) -> dict:
    return {"id": eff_id, "eff": kind, "eff_value": value, **extra}


CARDS = [
    _card("c_1008_srt4", ["c_1008_srt4_01", "c_1008_srt4_02", "c_1008_srt4_03"], "[TALENT_CELESTIAL,TALENT_RETAIN]"),
    _card("c_1055_srt4", ["c_1055_srt4_01", "c_1055_srt4_02", "c_1055_srt4_03"], "[TALENT_EXHAUST_2]"),
    _card("c_1055_uni3", ["c_1055_uni3_01", "c_1055_uni3_02"], "[TALENT_NO_COUNT]"),
    _card("c_1018_srt4", ["c_1018_srt4_01", "c_1018_srt4_02", "c_1018_srt4_03"], "[TALENT_NO_COUNT]"),
    _card("c_1004_uni2", ["c_1004_uni2_01", "c_1004_uni2_02"], "[TALENT_LEAD]"),
    _card("c_test_battle", ["c_test_battle_01"]),
    _card("c_test_missing", []),
    _card("c_test_fixed", ["c_test_fixed_01"], "[TALENT_UNIQUE_TEST]"),
]

EFFECTS = [
    _eff("c_1008_srt4_01", "SKILL_EFF_DMG", "120"),
    _eff("c_1008_srt4_02", "SKILL_EFF_SHIELD", "100"),
    _eff("c_1008_srt4_03", "SKILL_EFF_CS_SET_ADD", "1", link_cs_id="[cs01_0552]"),
    _eff("c_1055_srt4_01", "SKILL_EFF_CARD_DRAW", "1"),
    _eff("c_1055_srt4_02", "SKILL_EFF_CARD_TALENT_ADD", "2"),
    _eff("c_1055_srt4_03", "SKILL_EFF_CARD_DRAW", "1"),
    _eff("c_1055_uni3_01", "SKILL_EFF_DMG", "200", eff_attr="[DMG_ATTR_BASE_ON_DEF]"),
    _eff("c_1055_uni3_02", "SKILL_EFF_CS_SET_ADD", "1", link_cs_id="[cs01_1093]"),
    _eff("cs01_1093_01", "SKILL_EFF_DAMAGE_VALUE_ADD", "100"),
    _eff("c_1018_srt4_01", "SKILL_EFF_DMG", "120"),
    _eff("c_1018_srt4_02", "SKILL_EFF_DAMAGE_VALUE_ADD", "0", eff_condition_value_0="100"),
    _eff("c_1018_srt4_03", "SKILL_EFF_CS_SET_ADD", "1", link_cs_id="[cs01_0185]"),
    _eff("c_1004_uni2_01", "SKILL_EFF_SHIELD", "100"),
    _eff("c_1004_uni2_02", "SKILL_EFF_CS_SET_ADD", "1", link_cs_id="[cs01_0079]"),
    _eff("cs01_0079_01", "SKILL_EFF_DAMAGE_VALUE_ADD", "120"),
    _eff("c_test_battle_01", "SKILL_EFF_DMG", "80", eff_attr="[DMG_ATTR_FIX]"),
    _eff("c_test_fixed_01", "SKILL_EFF_DMG", "50", eff_attr="[DMG_ATTR_FIX]"),
]

STATUSES = [
    {"id": "cs01_1093", "link_skill_eff_id": "[cs01_1093_01]", "overlay_value_max": "MAX"},
    {"id": "cs01_0079", "link_skill_eff_id": "[cs01_0079_01]", "overlay_value_max": "5"},
    {"id": "cs01_0552", "link_skill_eff_id": "[]"},
    {"id": "cs01_0185", "link_skill_eff_id": "[]"},
]

TOOLTIPS = [
    {"id": "TALENT_CELESTIAL", "title": "tooltip@title@TALENT_CELESTIAL"},
    {"id": "TALENT_RETAIN", "title": "tooltip@title@TALENT_RETAIN"},
    {"id": "TALENT_EXHAUST_N", "title": "tooltip@title@TALENT_EXHAUST_N"},
    {"id": "TALENT_NO_COUNT", "title": "tooltip@title@TALENT_NO_COUNT"},
    {"id": "TALENT_LEAD", "title": "tooltip@title@TALENT_LEAD"},
    {"id": "TRIGGER_C1018_STANCE", "title": "tooltip@title@TRIGGER_C1018_STANCE"},
]

TEXT = {
    "card@desc@c_1008_srt4": "#result_coeff_ev_0# $Defense-Based Damage$ to all enemies<br>#result_coeff_ev_1# $Shield$<br>#result_coeff_ev_2# $Silver Veil$",
    "card@desc@c_1055_srt4": "Apply $Blessing$ to #result_ev_1# random card(s) in $Draw Pile$, then $Draw$ #result_ev_2# of those cards",
    "card@desc@c_1055_uni3": "#result_coeff_ev_0# $Defense-Based Damage$<br>+#cs_ev_1_0#% Damage Amount taken by the target for <cc>1</> turn",
    "card@desc@c_1018_srt4": "#result_damage_0# Damage<br>Gain $Dark Mist Stance$<br>^TRIGGER_C1018_STANCE^ Increase Damage Amount by #ecdv0_1#%",
    "card@desc@c_1004_uni2": "#result_damage_0# $Shield$<br>+[fc]<cc>{cal}#cs_ev_1_0#*#result_ev_1#{/}</>[/]% Damage Amount to the next $Bullet$ card $activate$d",
    "card@desc@c_test_battle": "#result_coeff_ev_0##n_result_damage_0# Damage for each#condition_value_stack_0_0# card ({cal}#cs_tv_cs01_0986#*#result_ev_0#{/}%)",
    "card@desc@c_test_missing": "Gain #result_ev_3# $AP$ and #mystery_token#",
    "card@desc@c_test_fixed": "#result_damage_0# fixed Damage",
    "card@name@c_1008_srt4": "Celestial Strike",
    "tooltip@title@talent_celestial": "Celestial",
    "tooltip@title@talent_retain": "Retain",
    "tooltip@title@talent_exhaust_n": "Exhaust",
    "tooltip@title@talent_no_count": "Haste",
    "tooltip@title@talent_lead": "Lead",
    "tooltip@title@trigger_c1018_stance": "Dark Mist Stance",
}


@pytest.fixture(scope="module")
def resolver(tmp_path_factory) -> TemplateResolver:
    root = write_client(tmp_path_factory.mktemp("client"), {
        "card(test)@card.json": CARDS,
        "card(test)@skill_eff.json": EFFECTS,
        "cs(test)@cs.json": STATUSES,
        "tooltip@tooltip.json": TOOLTIPS,
    }, TEXT)
    return TemplateResolver(Client(root), {"TALENT_UNIQUE_TEST": "Test Title"})


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Cards checked against the game


@pytest.mark.parametrize("card_id,expected", [
    ("c_1008_srt4", "[Celestial] [Retain] 120% Defense-Based Damage to all enemies\n100% Shield\n1 Silver Veil"),
    ("c_1055_srt4", "[Exhaust 2] Apply Blessing to 2 random card(s) in Draw Pile, then Draw 1 of those cards"),
    ("c_1055_uni3", "[Haste] 200% Defense-Based Damage\n+100% Damage Amount taken by the target for 1 turn"),
    ("c_1018_srt4", "[Haste] 120% Damage\nGain Dark Mist Stance\nDark Mist Stance: Increase Damage Amount by 100%"),
    ("c_1004_uni2", "[Lead] 100% Shield\n+120% Damage Amount to the next Bullet card activated"),
])
def test_cards_checked_against_the_game(resolver, card_id, expected):
    resolution = resolver.card_description(card_id)
    assert resolution.text == expected
    assert resolution.unresolved == []


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Edge cases


def test_battle_only_values_and_their_brackets_are_dropped(resolver):
    assert resolver.card_description("c_test_battle").text == "80 Damage for each card"


def test_unresolvable_placeholders_are_reported_and_kept(resolver):
    resolution = resolver.card_description("c_test_missing")
    assert resolution.unresolved == ["result_ev_3", "mystery_token"]
    assert "#result_ev_3#" in resolution.text


def test_fixed_damage_has_no_percent_and_override_titles_apply(resolver):
    assert resolver.card_description("c_test_fixed").text == "[Test Title] 50 fixed Damage"


def test_card_name(resolver):
    assert resolver.card_name("c_1008_srt4") == "Celestial Strike"
    assert resolver.card_name("c_unknown") is None


def test_status_max(resolver):
    assert resolver.resolve("max #cs_tv_max_cs01_0079#", []).text == "max 5"


@pytest.mark.parametrize("value,expected", [("120", "120"), ("12.0", "12"), ("0.5", "0.5"), ("MAX", "MAX"), (3.0, "3")])
def test_format_number(value, expected):
    assert format_number(value) == expected
