"""
Names and ids shared across targets: slugs, roman numerals, card types, class names and pinned legacy ids.
"""

from __future__ import annotations

import re

from scripts.datagen.client import parse_list
from scripts.datagen.overrides import Overrides
from scripts.datagen.runner import Context

# Epiphany levels as the deck builder and the guides write them, such as "Epiphany II".
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}

# The client's card categories the deck builder shows, by display name.
CARD_TYPES = {"CARD_ATK": "Attack", "CARD_SKILL": "Skill", "CARD_POWER": "Upgrade"}

# The overrides key that pins legacy output ids to client ids.
IDS_KEY = "_ids"

CLASS_TABLE = "base_class_define@base_class_define.json"

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str, max_length: int | None = None) -> str:
    """
    A lower-case, hyphenated id, such as "mei-lin" for "Mei Lin".

    Args:
        text: The text to turn into an id.
        max_length: Cut the id to this many characters, or keep it whole.

    Returns:
        The id, with no leading or trailing hyphen.
    """
    result = _SLUG.sub("-", text.casefold()).strip("-")
    return result if max_length is None else result[:max_length].strip("-")


def legacy_ids(overrides: Overrides, raw: dict | None = None) -> dict[str, str]:
    """
    The pinned output ids of a target, read from its overrides file.

    Args:
        overrides: The target's overrides. Its `_ids` directive is the map.
        raw: The `_ids` map itself, for tests. Read from `overrides` when omitted.

    Returns:
        client id -> pinned output id.
    """
    pinned = raw if raw is not None else overrides.directives.get(IDS_KEY, {})
    return {client_id: output_id for output_id, client_id in pinned.items()}


def class_names(ctx: Context, raw: str | None) -> list[str]:
    """
    Class ids from a client list cell, as the game names them.

    Args:
        ctx: The run context.
        raw: A cell such as "[striker,vanguard]".

    Returns:
        The display names in the cell's order, such as ["Striker", "Vanguard"].
    """
    classes = ctx.client.by_id(CLASS_TABLE)
    names = []
    for class_id in parse_list(raw):
        row = classes.get(class_id)
        names.append((ctx.client.text(row.get("class_name")) if row else None) or class_id.capitalize())
    return names


def card_type(ctx: Context, category: str | None) -> str:
    """
    A card category as the game names it.

    Args:
        ctx: The run context.
        category: Such as "CARD_ATK".

    Returns:
        Such as "Attack". The text key is the lower-cased category.
    """
    if not category:
        return ""
    return ctx.client.text(category.lower()) or category.removeprefix("CARD_").capitalize()
