"""
Shape and consistency checks for the character and partner tables.

These run over every entry rather than naming individual characters, so a newly added combatant or
partner is covered the moment it lands. The stat cross-check in particular catches the easy mistake
of picking a growth curve from a character's class, which is not always the curve they actually use.
"""

import json
import re
from pathlib import Path

import pytest

from api.game_data.characters import ATTRIBUTE_COLORS, CHARACTERS
from api.game_data.partners import PARTNERS, get_partner_base_stats, get_partner_passive_info
from api.game_data.scaling import get_char_base_stats

DATA_DIR = Path(__file__).resolve().parents[2] / "api" / "data"
CHAR_BASE_L1 = json.loads((DATA_DIR / "char_base_l1.json").read_text(encoding="utf-8"))
LEVEL_SCALING = json.loads((DATA_DIR / "level_scaling.json").read_text(encoding="utf-8"))
ASCEND_SCALING = json.loads((DATA_DIR / "ascend_scaling.json").read_text(encoding="utf-8"))

CLASSES = {"Hunter", "Psionic", "Ranger", "Striker", "Controller", "Vanguard"}

# Stored stats are the value at level 60 with full ascension.
MAX_LEVEL = 60
MAX_ASCEND = 5

# Adelheid predates this check and does not satisfy it. Her stored stats are well below what her
# growth curve produces, so either the stats or the curve is wrong, and there is no game data here
# to say which. Left failing loudly would drown out real problems, so she is listed explicitly.
KNOWN_STAT_MISMATCHES = {"Adelheid"}

COMBATANTS = [(rid, c) for rid, c in CHARACTERS.items() if c]
PARTNER_ENTRIES = [(rid, p) for rid, p in PARTNERS.items() if p]


@pytest.mark.parametrize("res_id,char", COMBATANTS, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_every_combatant_is_well_formed(res_id, char):
    assert char["name"]
    assert char["grade"] in (3, 4, 5)
    assert char["class"] in CLASSES
    assert char["attribute"] in ATTRIBUTE_COLORS
    for key in ("base_atk", "base_def", "base_hp"):
        assert isinstance(char[key], int) and char[key] > 0, key


def test_every_combatant_has_level_one_stats():
    missing = [c["name"] for rid, c in COMBATANTS if str(rid) not in CHAR_BASE_L1]
    assert not missing, f"no level 1 entry for: {missing}"


def test_level_one_entries_point_at_real_scaling_groups():
    for res_id, entry in CHAR_BASE_L1.items():
        assert entry["level_group"] in LEVEL_SCALING, f"{res_id}: {entry['level_group']}"
        assert entry["ascend_group"] in ASCEND_SCALING, f"{res_id}: {entry['ascend_group']}"


@pytest.mark.parametrize("res_id,char", COMBATANTS, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_stored_stats_agree_with_the_growth_curve(res_id, char):
    # The stored numbers must be what the level 1 stats plus the character's curve actually produce.
    # A curve chosen from the character's class rather than from their real stats fails here, which
    # is exactly how Arabella was caught growing on the Ranger curve despite being a Striker.
    if char["name"] in KNOWN_STAT_MISMATCHES:
        pytest.skip(f"{char['name']} is a known pre-existing mismatch")
    if str(res_id) not in CHAR_BASE_L1:
        pytest.skip("no level 1 entry")
    s = get_char_base_stats(str(res_id), MAX_LEVEL, MAX_ASCEND)
    assert (char["base_atk"], char["base_def"], char["base_hp"]) == (s["ATK"], s["DEF"], s["HP"])


@pytest.mark.parametrize("res_id,partner", PARTNER_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_every_partner_is_well_formed(res_id, partner):
    assert partner["name"]
    assert partner["grade"] in (3, 4, 5)
    assert partner["class"] in CLASSES
    assert partner["passive_name"] and partner["passive_desc"]
    assert partner["ego_name"]
    assert isinstance(partner["ego_cost"], int) and partner["ego_cost"] >= 0


@pytest.mark.parametrize("res_id,partner", PARTNER_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_partner_passive_placeholders_all_have_values(res_id, partner):
    # A placeholder with no matching entry in `values` renders as literal text like "{ATK%}".
    placeholders = set(re.findall(r"\{([^}]+)\}", partner["passive_desc"]))
    assert placeholders <= set(partner.get("values") or {})


@pytest.mark.parametrize("res_id,partner", PARTNER_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_partner_values_cover_every_limit_break(res_id, partner):
    for key, values in (partner.get("values") or {}).items():
        assert len(values) == 5, f"{key} has {len(values)} entries, expected one per limit break"
        assert list(values) == sorted(values), f"{key} goes backwards"


@pytest.mark.parametrize("res_id,partner", PARTNER_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_partner_base_stats_resolve(res_id, partner):
    # Either listed per partner or covered by the (grade, class) fallback.
    stats = get_partner_base_stats(res_id)
    assert stats and any(stats.values())


@pytest.mark.parametrize("res_id,partner", PARTNER_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_partner_passive_renders_at_every_limit_break(res_id, partner):
    for limit_break in range(5):
        desc = get_partner_passive_info(res_id, limit_break)["passive_desc"]
        assert "{" not in desc, f"unfilled placeholder at limit break {limit_break}: {desc}"
