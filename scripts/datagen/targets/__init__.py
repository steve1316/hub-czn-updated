"""
Every generator target, in the order a full run executes them.

A target module exposes `NAME`, `OFFLINE` (False when it needs the network) and `build(context) -> TargetResult`.
"""

from __future__ import annotations

from types import ModuleType

from scripts.datagen.targets import (
    card_art,
    char_presets,
    deck_builder,
    eff_type_catalog,
    encyclopedia_cards,
    enemy_presets,
    epiphanies,
    glossary,
    guides,
    items,
    monster_catalog,
    neutral_cards,
    persona_engravings,
    substat_rolls,
)

ALL_TARGETS: list[ModuleType] = [
    deck_builder,
    card_art,
    char_presets,
    items,
    neutral_cards,
    persona_engravings,
    substat_rolls,
    epiphanies,
    glossary,
    encyclopedia_cards,
    monster_catalog,
    enemy_presets,
    eff_type_catalog,
    guides,
]

OFFLINE_TARGETS: list[ModuleType] = [target for target in ALL_TARGETS if target.OFFLINE]


def by_name(name: str) -> ModuleType:
    """
    Look a target up by its `NAME`.

    Args:
        name: The target name.

    Returns:
        The target module.

    Raises:
        KeyError: If no target has that name.
    """
    for target in ALL_TARGETS:
        if target.NAME == name:
            return target
    raise KeyError(name)
