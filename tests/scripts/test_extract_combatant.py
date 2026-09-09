"""Tests for scripts/extract_combatant.py.

Strategy: run the extractor against res_ids whose CHARACTERS entries are
already known-good, then assert key fields match. If the game files were
re-extracted with the same content, output must equal CHARACTERS[res_id].
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from api.game_data.characters import CHARACTERS  # noqa: E402

from api.client_db import client_output_dir, have_client_db, have_client_text

OUTPUT_DIR = client_output_dir()

# Assisted extraction needs the unpacked game data, which is not in the repo.
pytestmark = pytest.mark.skipif(
    not (have_client_db() and have_client_text()),
    reason="game client DB or its text catalogue not available",
)


# Adelheid's nodes are stored the other way round from what the client says. `_DEF_SCALE_IDS` in
# api/routes/battle.py is built from `node_50 == "DEF%"`, so the order there is load bearing and
# "fixing" it would quietly change her damage. Left alone deliberately.
NODE_EXCEPTIONS = {1055}


@pytest.fixture(scope="module")
def extractor():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import extract_combatant  # noqa: WPS433 (local import is fine here)
    return extract_combatant


def test_yuki_1057_round_trip(extractor):
    """Yuki: Order/Striker/grade 5 — anchor for c_striker_green."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1057)
    expected = CHARACTERS[1057]
    assert entry["name"] == expected["name"]
    assert entry["grade"] == expected["grade"]
    assert entry["attribute"] == expected["attribute"]
    assert entry["class"] == expected["class"]
    assert entry["base_atk"] == expected["base_atk"]
    assert entry["base_def"] == expected["base_def"]
    assert entry["base_hp"] == expected["base_hp"]


def test_nia_1003_round_trip(extractor):
    """Nia: Instinct/Controller/grade 4 — anchor for c_controller_orange."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1003)
    expected = CHARACTERS[1003]
    assert entry["attribute"] == expected["attribute"]
    assert entry["class"] == expected["class"]
    assert entry["grade"] == expected["grade"]


def test_khalipe_1008_round_trip(extractor):
    """Khalipe: Instinct/Vanguard/grade 5 — anchor for c_knight_orange, RARITY_SSR."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1008)
    expected = CHARACTERS[1008]
    assert entry["attribute"] == expected["attribute"]
    assert entry["class"] == expected["class"]
    assert entry["grade"] == expected["grade"]


def test_magna_1010_round_trip(extractor):
    """Magna: Justice/Vanguard — anchor for c_knight_blue."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1010)
    expected = CHARACTERS[1010]
    assert entry["attribute"] == expected["attribute"]
    assert entry["class"] == expected["class"]


def test_rin_1018_round_trip(extractor):
    """Rin: Void/Striker — anchor for c_striker_purple."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1018)
    expected = CHARACTERS[1018]
    assert entry["attribute"] == expected["attribute"]
    assert entry["class"] == expected["class"]


def test_veronica_1033_round_trip(extractor):
    """Veronica: Passion/Ranger — anchor for c_ranger_red."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1033)
    expected = CHARACTERS[1033]
    assert entry["attribute"] == expected["attribute"]
    assert entry["class"] == expected["class"]


def test_adelheid_1055_is_vanguard_void_ssr(extractor):
    """Adelheid: display class+attr from char_base@char_base (c_knight_purple, RARITY_SSR)."""
    entry, _ = extractor.extract(OUTPUT_DIR, 1055)
    required = {"name", "grade", "attribute", "class", "base_atk",
                "base_def", "base_hp", "base_crit_rate", "base_crit_dmg",
                "base_weak_ego_dmg_rate", "node_50", "node_60"}
    assert required.issubset(entry.keys())
    assert entry["name"] == "Adelheid"
    assert entry["class"] == "Vanguard"
    assert entry["attribute"] == "Void"
    assert entry["grade"] == 5


def test_potential_nodes_reproduce_the_curated_table(extractor):
    # The old resolver built a prefix like "3011550" while the client's node ids read "30115_5_0_1",
    # so it silently returned None for everyone and every entry's nodes were typed in by hand.
    # Deriving all of them again is what says the replacement can be trusted to write a new entry.
    wrong = []
    for res_id, char in CHARACTERS.items():
        if not char or res_id in NODE_EXCEPTIONS:
            continue
        nodes, _from_layout = extractor.resolve_nodes(OUTPUT_DIR, res_id)
        if (nodes["node_50"], nodes["node_60"]) != (char["node_50"], char["node_60"]):
            wrong.append((res_id, char["name"], nodes, char["node_50"], char["node_60"]))
    assert not wrong, f"derived potential nodes disagree with the curated table: {wrong}"


def test_the_layout_fallback_agrees_with_the_effect_rows_wherever_both_exist(extractor):
    # A character released ahead of the effect table falls back to the tree layout. That is only
    # defensible while the two agree for the characters that have both, which they do from 30047 on.
    disagree = []
    for res_id, char in CHARACTERS.items():
        if not char or res_id < 30000:
            continue
        effect = extractor._effect_nodes(OUTPUT_DIR, res_id)
        layout = extractor._layout_nodes(OUTPUT_DIR, res_id)
        if effect and layout and effect != layout:
            disagree.append((res_id, char["name"], effect, layout))
    assert not disagree, f"the tree layout contradicts the effect rows: {disagree}"
