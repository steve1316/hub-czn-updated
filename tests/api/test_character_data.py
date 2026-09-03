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


def test_potential_node_percentages_match_the_game():
    # Read in game on Adelheid: a maxed Health node and a maxed Defense node both give 8%. HP% used
    # to top out at 3%, which understated Health for every character carrying that node.
    from api.game_data.characters import POTENTIAL_STAT_VALUES
    assert POTENTIAL_STAT_VALUES["HP%"][-1] == 8.0
    assert POTENTIAL_STAT_VALUES["DEF%"][-1] == 8.0
    assert POTENTIAL_STAT_VALUES["HP%"] == POTENTIAL_STAT_VALUES["DEF%"]


def test_potential_node_values_have_one_entry_per_node_level():
    from api.game_data.characters import POTENTIAL_STAT_VALUES
    for stat, values in POTENTIAL_STAT_VALUES.items():
        assert len(values) == 5, stat
        assert list(values) == sorted(values), stat


def test_adelheid_reaches_her_in_game_stats_with_maxed_nodes():
    # Base 419/191/443 at level 60 with full ascension, plus 8% Defense and 8% Health, gives the
    # 419/206/478 shown in game. Attack is untouched because she has no Attack node.
    base_def, base_hp = 191, 443
    assert int(base_def * 1.08) == 206
    assert int(base_hp * 1.08) == 478


def test_defence_scaling_characters_are_flagged_by_their_node():
    # node_50 == "DEF%" is what marks a character's damage as scaling off Defense rather than
    # Attack, so recording the nodes in the wrong order silently changes their damage.
    from api.routes.battle import _DEF_SCALE_IDS
    assert 1055 in _DEF_SCALE_IDS, "Adelheid's cards scale off Defense"
    for res_id in _DEF_SCALE_IDS:
        assert CHARACTERS[res_id]["node_50"] == "DEF%"


def test_every_character_has_potential_nodes_recorded():
    missing = [c["name"] for _rid, c in COMBATANTS if c["node_50"] is None or c["node_60"] is None]
    assert not missing, f"no potential node data for: {missing}"


# The extracted client database is the authority, but it is not in the repo, so these only run on a
# machine that has it. See docs/adding-a-character.md.
_CLIENT_COMBATANTS = None


def _client_combatants():
    """
    Combatant rows from the extracted client, keyed by res_id.

    Returns:
        res_id -> row, or None when the client data is not available.
    """
    global _CLIENT_COMBATANTS
    if _CLIENT_COMBATANTS is None:
        from api.client_db import client_db_dir
        path = client_db_dir() / "char_base@char_combatant.json"
        if not path.exists():
            _CLIENT_COMBATANTS = {}
        else:
            _CLIENT_COMBATANTS = {int(r["id"]): r for r in json.loads(path.read_text(encoding="utf-8"))}
    return _CLIENT_COMBATANTS


needs_client_db = pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "api").exists() or not _client_combatants(),
    reason="extracted client data not available",
)


@needs_client_db
def test_every_res_id_exists_in_the_client():
    # Fei was carried with a made up res_id until the client data settled it. Nothing should be
    # invented again without this failing.
    client = _client_combatants()
    unknown = [(rid, c["name"]) for rid, c in COMBATANTS if rid not in client]
    assert not unknown, f"res_ids that do not exist in the game: {unknown}"


@needs_client_db
def test_growth_curves_match_the_client():
    # Class does not determine the curve - Arabella is a Striker on the Ranger curve, which the
    # client confirms. This checks every character against the real table rather than guessing.
    client = _client_combatants()
    wrong = []
    for rid, _char in COMBATANTS:
        if rid not in client or str(rid) not in CHAR_BASE_L1:
            continue
        ours = CHAR_BASE_L1[str(rid)]["level_group"]
        theirs = client[rid]["link_combatant_level_group"]
        if ours != theirs:
            wrong.append((rid, ours, theirs))
    assert not wrong, f"level_group disagrees with the client: {wrong}"


@needs_client_db
def test_limit_break_groups_match_the_client():
    client = _client_combatants()
    wrong = []
    for rid, _char in COMBATANTS:
        if rid not in client or str(rid) not in CHAR_BASE_L1:
            continue
        ours = CHAR_BASE_L1[str(rid)]["limit_break_group"]
        theirs = client[rid].get("link_combatant_limit_break_group")
        if theirs and ours != theirs:
            wrong.append((rid, ours, theirs))
    assert not wrong, f"limit_break_group disagrees with the client: {wrong}"
