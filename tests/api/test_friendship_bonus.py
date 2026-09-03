"""
Friendship bonuses, checked against stats read out of the running game.

The HP column used to start at 1 instead of 3, which left every character 2 HP short from
friendship level 4 upwards. ATK and DEF were already right.
"""

import pytest

from api.game_data.constants import FRIENDSHIP_BONUSES, get_friendship_bonus
from api.game_data.scaling import get_char_base_stats


@pytest.mark.parametrize("level,expected", [(8, (9, 2, 6)), (10, (9, 3, 9))])
def test_bonus_matches_the_game(level, expected):
    # Read in game: Rin at friendship 8, Arabella at friendship 10.
    assert get_friendship_bonus(level) == expected


def test_table_follows_the_games_reward_cycle():
    # The game grants one stat per level on a repeating cycle from level 2:
    #   +3 Attack, then +1 Defense, then +3 Health.
    atk = dfn = hp = 0
    expected = {1: (0, 0, 0)}
    for lvl in range(2, len(FRIENDSHIP_BONUSES) + 1):
        step = (lvl - 2) % 3
        if step == 0:
            atk += 3
        elif step == 1:
            dfn += 1
        else:
            hp += 3
        expected[lvl] = (atk, dfn, hp)

    for lvl, a, d, h in FRIENDSHIP_BONUSES:
        assert (a, d, h) == expected[lvl], f"level {lvl}"


def test_no_bonus_before_level_four():
    for lvl in (1, 2, 3):
        assert get_friendship_bonus(lvl)[2] == 0


def test_every_column_only_ever_grows():
    prev = (0, 0, 0)
    for _lvl, atk, dfn, hp in FRIENDSHIP_BONUSES:
        assert (atk, dfn, hp) >= prev
        prev = (atk, dfn, hp)


def test_rin_character_sheet_reconstructs_exactly():
    # Rin, level 20, ascend 1, friendship 8 -> 258/79/186 on her in-game sheet. This is the check
    # that base scaling and friendship line up, which is what proved the scaling itself was fine.
    base = get_char_base_stats("1018", 20, 1)
    atk, dfn, hp = get_friendship_bonus(8)
    assert (base["ATK"] + atk, base["DEF"] + dfn, base["HP"] + hp) == (258, 79, 186)
