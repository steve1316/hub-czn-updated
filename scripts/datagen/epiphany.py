"""
A card's epiphany variants with the names and costs the game shows, and the divine and common epiphany catalogs.

Shared by the deck builder and the Guides import, so both name an epiphany the same way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache

from scripts.datagen.naming import ROMAN
from scripts.datagen.runner import REPO_ROOT, Context

EPIPHANY_DATA_DIR = REPO_ROOT / "src/pages/deck-builder/data"
DIVINE_FILE = "deck-builder-divine-epiphanies.json"
COMMON_FILE = "deck-builder-common-epiphanies.json"

# An extra line that lowers the card's cost by one, such as a divine "Reduce Cost of this card by 1.".
REDUCE_COST = "Reduce Cost of this card by 1"

# A transformed card such as Shard:Light (`c_30134_srt4_mut1`) has the variants of the card it came from, each transformed the same way.
_TRANSFORMED = re.compile(r"^(c_\d+_\w+?)(_mut\d+)$")


@dataclass(frozen=True)
class Variant:
    """One level of a card: the base card at level 0, or an epiphany at 1-5."""

    # 0 for the base card, else the epiphany level.
    level: int
    # The client card id for this level.
    card_id: str
    # The game's name for this level, or the base name with a numeral when the game gives none.
    name: str
    # The cost printed on the card, -1 for an X cost.
    cost: int
    # The resolved card text.
    text: str


@dataclass(frozen=True)
class Extra:
    """A divine or common epiphany line added to a card."""

    # The catalog id, such as "div_0098" or "com_0065".
    id: str
    # The divine god's display name, None for a common epiphany.
    god: str | None
    # The line as the card shows it.
    text: str


def epiphany_name(base_name: str, level: int, game_name: str | None) -> str:
    """
    The display name of a card's epiphany.

    Args:
        base_name: The base card's name.
        level: The epiphany level, 1-5.
        game_name: The game's own name for the variant card, if any.

    Returns:
        The game name when it differs from the base name ("Flicker Blade (Unbound)"), else the base name and a numeral ("Sword Resonance II").
    """
    if game_name and game_name != base_name:
        return game_name
    return f"{base_name} {ROMAN.get(level, level)}"


def card_cost(cost: int, extra: Extra | None) -> int:
    """
    The cost a card shows once an extra line is added.

    Args:
        cost: The variant's own cost, -1 for X.
        extra: The divine or common line, if any.

    Returns:
        The cost, one lower (never below 0) when the line reduces it. An X cost is never reduced.
    """
    if cost >= 0 and extra and extra.text.startswith(REDUCE_COST):
        return max(cost - 1, 0)
    return cost


def variants(ctx: Context, base_id: str) -> list[Variant]:
    """
    A card and its epiphany variants.

    Args:
        ctx: The run context.
        base_id: The base card id, or a transformed card id such as `c_30134_srt4_mut1`.

    Returns:
        The base card at level 0 then levels 1-5, or an empty list when the card has no variants.
    """
    transformed = _TRANSFORMED.match(base_id)
    parent, suffix = (transformed.group(1), transformed.group(2)) if transformed else (base_id, "")
    levels = [(level, card_id + suffix) for level, card_id in ctx.client.variants_by_base.get(parent, [])]
    levels = [(level, card_id) for level, card_id in levels if card_id in ctx.client.cards]
    if not levels or base_id not in ctx.client.cards:
        return []
    base_name = ctx.resolver.card_name(base_id) or base_id
    found = [Variant(0, base_id, base_name, printed_cost(ctx, base_id), _text(ctx, base_id, None))]
    for level, card_id in levels:
        name = epiphany_name(base_name, level, ctx.resolver.card_name(card_id))
        found.append(Variant(level, card_id, name, printed_cost(ctx, card_id), _text(ctx, card_id, base_id)))
    return found


def base_text(ctx: Context, card_id: str) -> str:
    """
    A card's own text.

    Args:
        ctx: The run context.
        card_id: A client card id.

    Returns:
        The resolved text, for a card that has no epiphanies to take it from.
    """
    return _text(ctx, card_id, None)


def printed_cost(ctx: Context, card_id: str) -> int:
    """
    The cost printed on a card.

    Args:
        ctx: The run context.
        card_id: A client card id.

    Returns:
        The cost, -1 for an X cost.
    """
    return int(ctx.client.cards[card_id].get("cost", 0) or 0)


@cache
def divine_epiphanies() -> list[Extra]:
    """
    Every divine epiphany.

    Returns:
        The catalog in file order, each with its god.
    """
    return [Extra(row["id"], row["display_god"], row["description"]) for row in _catalog(DIVINE_FILE)]


@cache
def common_epiphanies() -> list[Extra]:
    """
    Every common epiphany.

    Returns:
        The catalog in file order, with no god.
    """
    return [Extra(row["id"], None, row["description"]) for row in _catalog(COMMON_FILE)]


@cache
def divine_gods() -> dict[str, str]:
    """
    The divine gods' display names.

    Returns:
        Lowercase client god name (the stem of its icon file, such as "vitor") -> display name ("Vytor").
    """
    return {row["god"].lower(): row["display_god"] for row in _catalog(DIVINE_FILE)}


def _catalog(name: str) -> list[dict]:
    return json.loads((EPIPHANY_DATA_DIR / name).read_text(encoding="utf-8"))


def _text(ctx: Context, card_id: str, base_id: str | None) -> str:
    return ctx.text(ctx.resolver.card_description(card_id, base_card_id=base_id).text)
