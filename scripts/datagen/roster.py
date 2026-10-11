"""
The characters the app ships, as the generators see them.

`characters.py` is written by `scripts/add_character.py` (the Apply step), so it is the source of truth for which
combatants the app knows. The client also lists test and unreleased rows, which this deliberately leaves out.
"""

from __future__ import annotations

from functools import cache

from api.game_data.characters import CHARACTERS


@cache
def combatants() -> dict[int, dict]:
    """
    Every shipped combatant, worked out once per process.

    Returns:
        res_id -> its `CHARACTERS` entry, without the table's empty placeholder entries. Shared, so callers must not mutate it.
    """
    return {res_id: entry for res_id, entry in CHARACTERS.items() if entry}


def by_name() -> list[tuple[int, dict]]:
    """
    Shipped combatants in display order.

    Returns:
        (res_id, entry) pairs sorted by name, case-insensitively.
    """
    return sorted(combatants().items(), key=lambda item: item[1]["name"].casefold())
