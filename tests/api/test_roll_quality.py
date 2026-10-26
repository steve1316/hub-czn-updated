"""
Gear Score stays on the Legendary scale so pieces compare across rarities, while roll quality and the potential range follow the
piece's own rarity.
"""

from api.models.memory_fragment import MemoryFragment

# Rarity digits in a piece res_id: slot 1, then rarity, then set 031.
RARE = 3
LEGEND = 4


def _piece(rarity: int, level: int, subs: list[tuple[str, float]]) -> MemoryFragment:
    """
    A parsed piece with one roll per substat.

    Args:
        rarity: The rarity digit.
        level: The reinforce level.
        subs: (stat id, value) for each substat.

    Returns:
        The piece with its Gear Score and potential worked out.
    """
    stat_list = [{"stat": "S_ATK_INC_ADD_OUT", "slot": 0, "type": 0, "value": 20}]
    stat_list += [{"stat": stat, "slot": i + 1, "type": 1, "value": value} for i, (stat, value) in enumerate(subs)]
    piece = MemoryFragment.from_json({"id": 1, "res_id": int(f"11{1}{rarity}031"), "level": level, "stat_list": stat_list})
    piece.calculate_base_score()
    piece.calculate_potential()
    return piece


def test_rare_best_roll_is_full_quality_but_scores_on_the_legendary_scale():
    piece = _piece(RARE, 4, [("S_ATK_INC_ADD_OUT", 7)])
    sub = piece.substats[0]
    assert sub.get_efficiency() == 100
    assert sub.rolls[0].is_max_roll is True
    assert piece.gear_score == 8.8


def test_legendary_best_roll_is_full_quality_and_full_score():
    piece = _piece(LEGEND, 5, [("S_ATK_INC_ADD_OUT", 8)])
    assert piece.substats[0].get_efficiency() == 100
    assert piece.gear_score == 10.0


def test_potential_counts_one_roll_per_level_left():
    # A fresh Legendary has 5 levels left: one new substat and four upgrades.
    piece = _piece(LEGEND, 0, [("S_ATK_INC_ADD_OUT", 8), ("S_ATK_INC_RATE_OUT", 1.3), ("S_CRI_INC_ADD", 2.0)])
    assert piece.gear_score == 30.0
    assert piece.potential_high == 80.0
    assert piece.potential_low == 60.0


def test_rare_potential_is_capped_by_rare_rolls():
    piece = _piece(RARE, 0, [("S_ATK_INC_ADD_OUT", 7)])
    assert piece.potential_high == round(8.8 + 4 * 7 / 8 * 10, 1)
    assert piece.potential_low == round(8.8 + 4 * 4 / 8 * 10, 1)


def test_maxed_piece_has_no_potential_left():
    piece = _piece(RARE, 4, [("S_ATK_INC_ADD_OUT", 7)])
    assert piece.potential_low == piece.potential_high == piece.gear_score
