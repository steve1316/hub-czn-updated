"""
Tests for the Memory Fragment set extractor.

The fixtures mirror the shapes that matter in the real client: a two-piece stat set, a four-piece
conditional set with no two-piece tier, and a set that exists in the table but has no pieces in the
game yet.
"""

from pathlib import Path

import pytest

from scripts.extract_sets import extract_sets

FIXTURES = Path(__file__).parent / "fixtures" / "sets"


@pytest.fixture(scope="module")
def extracted():
    return extract_sets(FIXTURES)


def test_only_sets_with_pieces_in_the_game_are_extracted(extracted):
    """Set 21 is in the client table but nothing links to it, so it is not a set players can own."""
    assert sorted(extracted) == [7, 20, 30, 31]


def test_two_piece_stat_set_is_scorable(extracted):
    tetra = extracted[7]
    assert tetra["name"] == "Tetra's Authority"
    assert tetra["pieces"] == 2
    assert tetra["type"] == "stat"
    assert tetra["stat"] == "DEF%"
    assert tetra["value"] == 12


def test_curly_apostrophes_are_normalised(extracted):
    """The client mixes ' and U+2019 in set names. The table uses ASCII throughout."""
    assert "\u2019" not in extracted[7]["name"]


def test_four_piece_conditional_set_has_no_two_piece_bonus(extracted):
    """Line of Justice has no set2 tier in the client, so it must not gain one here."""
    justice = extracted[20]
    assert justice["pieces"] == 4
    assert justice["type"] == "conditional"
    assert "two_piece" not in justice


def test_multi_line_descriptions_are_flattened(extracted):
    assert "<br>" not in extracted[20]["bonus"]
    assert extracted[20]["bonus"] == "+20% Crit of Order cards | second line"


def test_icon_path_is_set_only_when_the_client_has_art(extracted):
    assert extracted[7]["icon_path"] == "/assets/pieces/icon_piece_set_007.png"


def test_colour_markup_is_stripped(extracted):
    """The client wraps attribute names in <color_...> tags that mean nothing outside its own UI."""
    bonus = extracted[20]["bonus"]
    assert "<color" not in bonus and "</>" not in bonus


def test_a_stat_the_optimizer_cannot_score_is_reported(capsys):
    """Silently downgrading it to conditional would hide a bonus the game really does grant."""
    result = extract_sets(FIXTURES)
    err = capsys.readouterr().err
    assert "S_CRI_INC_ADD" in err, f"unmapped stat link was not reported: {err!r}"
    assert result[30]["type"] == "conditional"
    assert "stat" not in result[30]


def test_a_six_piece_tier_is_reported(capsys):
    """SETS models 2 and 4 piece counts only, so a 6-piece tier needs a human before it is pasted."""
    extract_sets(FIXTURES)
    err = capsys.readouterr().err
    assert "6-piece" in err, f"six-piece tier was not reported: {err!r}"


def test_a_six_piece_set_keeps_its_two_piece_bonus(extracted):
    """The sub-bonus rule is keyed off the lower tier, not off the main tier being exactly 4."""
    assert extracted[31]["pieces"] == 6
    assert extracted[31]["two_piece"] == {"stat": "ATK%", "value": 9}
