"""
Per-character piece recommendations derived from piece_valid_setting game data.
Generated from piece_valid_setting@piece_valid_setting.json.
"""

from game_data.constants import ALL_STAT_NAMES


_RAW: dict[int, dict] = {
    1003: {
        "sets":    [7, 8, 10],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%'],
        "main_6":  ['DEF%', 'Ego'],
        "substats":['Flat DEF', 'DEF%', 'Ego'],
    },
    1004: {
        "sets":    [15, 11],
        "main_4":  ['CRate', 'CDmg', 'ATK%'],
        "main_5":  ['Order DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Order DMG%'],
    },
    1005: {
        "sets":    [18, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['Passion DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Passion DMG%'],
    },
    1008: {
        "sets":    [7, 11, 8],
        "main_4":  ['CRate', 'CDmg', 'HP%'],
        "main_5":  ['Instinct DMG%', 'ATK%', 'HP%'],
        "main_6":  ['DEF%'],
        "substats":['Flat DEF', 'DEF%', 'CRate', 'CDmg', 'Instinct DMG%'],
    },
    1009: {
        "sets":    [16, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['Void DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'DoT%', 'Void DMG%'],
    },
    1010: {
        "sets":    [7, 8, 11],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%', 'Justice DMG%'],
        "main_6":  ['DEF%', 'HP%'],
        "substats":['Flat DEF', 'DEF%', 'Flat HP', 'HP%', 'Justice DMG%'],
    },
    1012: {
        "sets":    [11, 9, 8],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['Order DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Order DMG%'],
    },
    1017: {
        "sets":    [7, 11, 8],
        "main_4":  ['CRate', 'CDmg', 'HP%'],
        "main_5":  ['Order DMG%', 'HP%'],
        "main_6":  ['DEF%'],
        "substats":['Flat DEF', 'DEF%', 'CRate', 'CDmg', 'Order DMG%'],
    },
    1018: {
        "sets":    [6, 11],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Void DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Void DMG%'],
    },
    1021: {
        "sets":    [18, 11],
        "main_4":  ['CDmg', 'CRate', 'ATK%'],
        "main_5":  ['Passion DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Passion DMG%'],
    },
    1024: {
        "sets":    [25, 7],
        "main_4":  ['HP%', 'ATK%'],
        "main_5":  ['HP%', 'Instinct DMG%', 'ATK%'],
        "main_6":  ['DEF%'],
        "substats":['Flat DEF', 'DEF%', 'Ego', 'Instinct DMG%'],
    },
    1027: {
        "sets":    [18, 11],
        "main_4":  ['CDmg', 'CRate', 'ATK%'],
        "main_5":  ['ATK%', 'Passion DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Passion DMG%'],
    },
    1028: {
        "sets":    [7, 8, 11],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%', 'Passion DMG%'],
        "main_6":  ['DEF%', 'HP%'],
        "substats":['Flat DEF', 'DEF%', 'Flat HP', 'HP%', 'Passion DMG%'],
    },
    1033: {
        "sets":    [18, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Passion DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Passion DMG%'],
    },
    1039: {
        "sets":    [7, 8, 10],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%'],
        "main_6":  ['DEF%', 'Ego'],
        "substats":['Flat DEF', 'DEF%', 'Ego'],
    },
    1040: {
        "sets":    [11, 9, 8],
        "main_4":  ['CDmg', 'CRate', 'ATK%'],
        "main_5":  ['Justice DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Justice DMG%'],
    },
    1041: {
        "sets":    [6, 11],
        "main_4":  ['CRate', 'CDmg', 'ATK%'],
        "main_5":  ['Void DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Void DMG%'],
    },
    1043: {
        "sets":    [9, 11, 8],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Order DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Order DMG%'],
    },
    1049: {
        "sets":    [25, 8],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%'],
        "main_6":  ['HP%', 'Ego'],
        "substats":['Flat HP', 'HP%', 'Ego'],
    },
    1050: {
        "sets":    [8, 9, 7],
        "main_4":  ['HP%', 'ATK%'],
        "main_5":  ['HP%', 'Passion DMG%', 'ATK%'],
        "main_6":  ['HP%', 'ATK%'],
        "substats":['Flat ATK', 'ATK%', 'Flat HP', 'HP%', 'Passion DMG%'],
    },
    1052: {
        "sets":    [7, 8, 11],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%', 'Instinct DMG%', 'ATK%'],
        "main_6":  ['DEF%', 'HP%'],
        "substats":['Flat DEF', 'DEF%', 'Flat HP', 'HP%', 'Instinct DMG%'],
    },
    1055: {
        "sets":    [27, 7],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%', 'Void DMG%', 'ATK%'],
        "main_6":  ['DEF%', 'HP%'],
        "substats":['Flat DEF', 'DEF%', 'Flat HP', 'HP%', 'Void DMG%'],
    },
    1056: {
        "sets":    [9, 8, 10],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Void DMG%', 'HP%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'Ego', 'Void DMG%'],
    },
    1057: {
        "sets":    [15, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Order DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Order DMG%'],
    },
    1060: {
        "sets":    [22, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Void DMG%'],
        "main_6":  ['ATK%', 'HP%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Void DMG%'],
    },
    1061: {
        "sets":    [26, 11],
        "main_4":  ['CRate', 'CDmg', 'ATK%'],
        "main_5":  ['Passion DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Passion DMG%'],
    },
    1062: {
        "sets":    [20, 11],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Justice DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Justice DMG%'],
    },
    1064: {
        "sets":    [16, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Void DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Void DMG%'],
    },
    1069: {
        "sets":    [10, 9, 11],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Passion DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Passion DMG%'],
    },
    30047: {
        "sets":    [24, 7],
        "main_4":  ['CRate', 'CDmg'],
        "main_5":  ['Order DMG%', 'ATK%', 'HP%'],
        "main_6":  ['DEF%', 'HP%'],
        "substats":['Flat DEF', 'DEF%', 'CRate', 'CDmg', 'Order DMG%'],
    },
    30048: {
        "sets":    [28, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Void DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Void DMG%'],
    },
    30075: {
        "sets":    [23, 11],
        "main_4":  ['CRate', 'CDmg', 'ATK%'],
        "main_5":  ['Instinct DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Instinct DMG%'],
    },
    30084: {
        "sets":    [25, 7],
        "main_4":  ['HP%', 'CRate', 'CDmg'],
        "main_5":  ['HP%', 'Order DMG%'],
        "main_6":  ['DEF%'],
        "substats":['Flat DEF', 'DEF%', 'Ego', 'Order DMG%'],
    },
    30093: {
        "sets":    [26, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Passion DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Passion DMG%'],
    },
    30097: {
        "sets":    [24, 9],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['ATK%', 'Justice DMG%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Justice DMG%'],
    },
    30113: {
        "sets":    [28, 11],
        "main_4":  ['CRate', 'CDmg', 'ATK%'],
        "main_5":  ['Instinct DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'Instinct DMG%'],
    },
    30115: {
        "sets":    [29, 11],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['Instinct DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'DoT%', 'Instinct DMG%'],
    },
    30117: {
        "sets":    [29, 11],
        "main_4":  ['ATK%', 'CRate', 'CDmg'],
        "main_5":  ['Instinct DMG%', 'ATK%'],
        "main_6":  ['ATK%'],
        "substats":['Flat ATK', 'ATK%', 'CRate', 'CDmg', 'DoT%', 'Instinct DMG%'],
    },
}


_MAIN_STAT_ONLY = frozenset([
    'Passion DMG%', 'Order DMG%', 'Justice DMG%', 'Void DMG%', 'Instinct DMG%',
])


def get_char_preset(char_id: int) -> dict | None:
    """
    Returns scoring preset for a character or None if not found.
    Result shape:
        recommended_sets: list[int]   -- set numeric IDs in priority order
        main_stat_4/5/6: list[str]    -- recommended main stats, first = best
        substats:        list[str]    -- recommended substats, first = best
        weights:         dict[str,int]-- suggested scoring weights (0-10)
    """
    raw = _RAW.get(char_id)
    if raw is None:
        return None
    substats = [s for s in raw["substats"] if s not in _MAIN_STAT_ONLY]
    weights: dict[str, int] = {name: 1 for name in ALL_STAT_NAMES}
    for stat in substats:
        if stat in weights:
            weights[stat] = 8
    return {
        "recommended_sets": raw["sets"],
        "main_stat_4":      raw["main_4"],
        "main_stat_5":      raw["main_5"],
        "main_stat_6":      raw["main_6"],
        "substats":         substats,
        "weights":          weights,
    }


CHAR_IDS_WITH_PRESET: frozenset[int] = frozenset(_RAW.keys())