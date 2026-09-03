"""
Arabella (30115) and her Partner Licinia (30116).

Added from community sources plus stats read straight out of the game, because the client DB is
locked inside the game's data.pack. These pin the values that were cross-checked, so a later
extraction that disagrees shows up as a failure rather than a silent change.
"""

import json
from pathlib import Path

import pytest

from api.game_data.characters import CHARACTERS
from api.game_data.partners import PARTNERS, PARTNER_BASE_STATS, get_partner_base_stats, get_partner_passive_info
from api.game_data.scaling import get_char_base_stats

ARABELLA = 30115
LICINIA = 30116

CHAR_BASE_L1 = json.loads(
    (Path(__file__).resolve().parents[2] / "api" / "data" / "char_base_l1.json").read_text(encoding="utf-8")
)


def test_arabella_identity():
    c = CHARACTERS[ARABELLA]
    assert c["name"] == "Arabella"
    assert c["grade"] == 5
    assert c["class"] == "Striker"
    assert c["attribute"] == "Instinct"


def test_arabella_level_one_stats_match_the_game():
    entry = CHAR_BASE_L1[str(ARABELLA)]
    assert (entry["atk"], entry["def"], entry["hp"]) == (160, 45, 90)
    assert (entry["cri"], entry["cri_dmg"]) == (3.0, 125.0)


def test_arabella_grows_on_the_ranger_curve_not_the_striker_one():
    # She is a Striker, but her level 1 (160/45/90) and level 60 (513/152/346) only add up on the
    # Ranger curve. Assuming her class picked the curve produced numbers that were plainly wrong.
    assert CHAR_BASE_L1[str(ARABELLA)]["level_group"] == "c_lv_ranger_ssr"

    strikers = [c for r, c in CHARACTERS.items()
                if c and r != ARABELLA and c["grade"] == 5 and c["class"] == "Striker"]
    assert strikers, "no other 5-star Strikers to compare against"
    a = CHARACTERS[ARABELLA]
    for other in strikers:
        assert (a["base_atk"], a["base_def"], a["base_hp"]) != (other["base_atk"], other["base_def"], other["base_hp"])


def test_arabella_stored_stats_follow_the_same_convention_as_everyone_else():
    # Every entry in CHARACTERS holds the row 60 value, so hers does too.
    s = get_char_base_stats(str(ARABELLA), 60, 5)
    assert (s["ATK"], s["DEF"], s["HP"]) == (495, 146, 332)
    a = CHARACTERS[ARABELLA]
    assert (a["base_atk"], a["base_def"], a["base_hp"]) == (495, 146, 332)


def test_arabella_matches_the_game_at_its_displayed_level_sixty():
    # The game shows 513/152/346, which is this table's last row rather than row 60. Every character
    # is off by those same two rows, so that is a separate problem and not specific to her.
    s = get_char_base_stats(str(ARABELLA), 62, 5)
    assert (s["ATK"], s["DEF"], s["HP"]) == (513, 152, 346)


def test_the_two_row_offset_holds_for_existing_characters_too():
    # Read out of the game: Haru 483/161/394 and Heidemarie 533/147/331 at its level 60 display.
    for res_id, expected in ((1062, (483, 161, 394)), (30093, (533, 147, 331))):
        s = get_char_base_stats(str(res_id), 62, 5)
        assert (s["ATK"], s["DEF"], s["HP"]) == expected


def test_licinia_identity():
    p = PARTNERS[LICINIA]
    assert p["name"] == "Licinia"
    assert p["grade"] == 5
    assert p["class"] == "Striker"
    assert p["ego_name"] == "Blossoming Venom"
    assert p["ego_cost"] == 3


@pytest.mark.parametrize("limit_break,expected", [(0, "16%"), (4, "24%")])
def test_licinia_attack_bonus_scales_with_limit_break(limit_break, expected):
    desc = get_partner_passive_info(LICINIA, limit_break)["passive_desc"]
    assert f"Attack by {expected}" in desc


def test_licinia_falls_back_to_the_class_base_stats():
    # Deliberately not in PARTNER_BASE_STATS, matching how Clara was added. The (5, Striker)
    # fallback is the same value every other 5-star Striker partner uses.
    assert LICINIA not in PARTNER_BASE_STATS
    assert get_partner_base_stats(LICINIA) == {"atk": 118, "def": 0, "hp": 119}
