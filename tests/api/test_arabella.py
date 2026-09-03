"""
Arabella (30115) and her Partner Licinia (30116).

Added from community sources rather than the client DB, which is locked inside the game's data.pack.
These pin the values that were cross-checked against the existing class templates, so a later
extraction that disagrees shows up as a failure rather than a silent change.
"""

import pytest

from api.game_data.characters import CHARACTERS
from api.game_data.partners import PARTNERS, get_partner_base_stats, get_partner_passive_info

ARABELLA = 30115
LICINIA = 30116


def test_arabella_identity():
    c = CHARACTERS[ARABELLA]
    assert c["name"] == "Arabella"
    assert c["grade"] == 5
    assert c["class"] == "Striker"
    assert c["attribute"] == "Instinct"


def test_arabella_matches_the_five_star_striker_template():
    # Every other 5-star Striker shares these level 60 values. Community sites quote 495/146/332,
    # which appears to include ascension, so the template is used instead.
    others = [c for r, c in CHARACTERS.items()
              if c and r != ARABELLA and c["grade"] == 5 and c["class"] == "Striker"]
    assert others, "no other 5-star Strikers to compare against"
    a = CHARACTERS[ARABELLA]
    for other in others:
        assert (a["base_atk"], a["base_def"], a["base_hp"]) == \
               (other["base_atk"], other["base_def"], other["base_hp"])


def test_arabella_has_level_one_stats():
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).resolve().parents[2] / "api" / "data" / "char_base_l1.json").read_text(encoding="utf-8"))
    entry = data[str(ARABELLA)]
    assert (entry["atk"], entry["def"], entry["hp"]) == (160, 45, 90)
    assert entry["level_group"] == "c_lv_striker_ssr"


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
    from api.game_data.partners import PARTNER_BASE_STATS
    assert LICINIA not in PARTNER_BASE_STATS
    assert get_partner_base_stats(LICINIA) == {"atk": 118, "def": 0, "hp": 119}
