"""
The deck builder's shared card pool: neutral, seasonal, encounter, Persona and monster cards any combatant can add.

Rows come from six client card shards, filtered by their `sort` column. Saved decks store card ids, so every card the
hand-written file used to list keeps its old `n_*` / `m_*` id through the `_ids` map in the overrides file, and is always
kept. A card that is new to the app takes its client id instead, so no id ever has to be handed out by hand again.
"""

from __future__ import annotations

from pathlib import Path

from scripts.datagen.art import wanted, webp
from scripts.datagen.client import parse_list
from scripts.datagen.naming import RARITIES, card_type, class_names, legacy_ids
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.runner import Context, TargetResult, json_bytes

NAME = "neutral_cards"
OFFLINE = True

OUTPUT_PATH = Path("src/pages/deck-builder/data/deck-builder-neutral-cards.json")
DATA_DIR = Path("src/pages/deck-builder/data")
IMAGE_DIR = Path("neutral-cards")

EXTRA_TAG_TABLE = "extra_tag@extra_tag.json"

# Card shard -> the `sort` values it contributes, or None for every row. Legacy ids are kept whatever their sort.
SOURCES: dict[str, tuple[str, ...] | None] = {
    "public": None,
    "disaster": None,
    "encounter": ("SORT_ETC",),
    "eidolon": ("SORT_EIDOLON",),
    "monster": ("SORT_MONSTER_UNIQUE",),
    "etc": (),
}

# Cards from this shard are monster cards. Everything else is neutral.
MONSTER_SHARD = "monster"

# Forbidden cards are the ones the client sorts as taboo.
TABOO_SORT = "SORT_TABOO"

# An extra tag of this type marks a card that belongs to one Chaos season, such as `ds03`.
SEASON_TAG_TYPE = "DISASTER_SEASON"

# Deck builder art is a 200x300 WebP thumbnail of the client illustration.
IMAGE_SIZE = (200, 300)
IMAGE_QUALITY = 80


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Build


def build(ctx: Context) -> TargetResult:
    """
    Generate the shared card pool and any missing card art.

    Args:
        ctx: The run context.

    Returns:
        The JSON file, the art to add, a summary, and any unresolved placeholders, broken ids or invalid overrides.
    """
    overrides = ctx.overrides(NAME)
    pinned = legacy_ids(overrides)
    issues: list[Issue] = []
    rows = select_rows(ctx, pinned, overrides, issues)
    season_tags = _season_tags(ctx)

    generated: dict[str, dict] = {}
    rows_by_output: dict[str, dict] = {}
    for shard, row in rows:
        entry = card_entry(ctx, shard, row, pinned.get(row["id"], row["id"]), season_tags, issues, overrides)
        generated[entry["id"]] = entry
        rows_by_output[entry["id"]] = row

    issues.extend(overrides.validate(generated))
    cards = sorted(overrides.apply(generated).values(), key=sort_key)

    new_files: dict[Path, bytes] = {}
    for card in cards:
        path = DATA_DIR / card["image_path"]
        if not wanted(ctx, path):
            continue
        row = rows_by_output[card["id"]]
        source = ctx.client.illustration(row, columns=("sct_name",))
        if source is not None:
            new_files[path] = webp(source, quality=IMAGE_QUALITY, size=IMAGE_SIZE)
        else:
            issues.append(Issue("warning", f"{NAME}: no illustration in the client for {card['id']} ({row.get('sct_name')}.png)"))

    monsters = sum(card["category"] == "monster" for card in cards)
    summary = f"{len(cards) - monsters} neutral and {monsters} monster cards, {len(new_files)} image(s) to add"
    return TargetResult({OUTPUT_PATH: json_bytes(cards)}, summary, issues, new_files=new_files)


def select_rows(ctx: Context, pinned: dict[str, str], overrides: Overrides, issues: list[Issue]) -> list[tuple[str, dict]]:
    """
    The client card rows that belong in the shared pool.

    Args:
        ctx: The run context.
        pinned: client id -> legacy output id. These rows are always kept.
        overrides: The target's overrides, whose `_exclude` / `_include` patterns filter rows.
        issues: A pinned id that is missing from the client is reported here.

    Returns:
        (shard, row) pairs in shard and file order.
    """
    selected = []
    seen: set[str] = set()
    for shard, sorts in SOURCES.items():
        for row in ctx.client.rows(f"card({shard})@card.json"):
            card_id = row.get("id", "")
            in_source = sorts is None or row.get("sort") in sorts
            if (in_source or card_id in pinned) and overrides.keeps(card_id) and card_id not in seen:
                selected.append((shard, row))
                seen.add(card_id)
    for card_id in sorted(set(pinned) - seen):
        issues.append(Issue("error", f"{NAME}: pinned id {pinned[card_id]} points at {card_id}, which is not a kept card in the client"))
    return selected


def card_entry(ctx: Context, shard: str, row: dict, output_id: str, season_tags: set[str], issues: list[Issue], overrides: Overrides) -> dict:
    """
    One card in the output's format.

    Args:
        ctx: The run context.
        shard: The card shard the row came from, such as "public".
        row: The client card row.
        output_id: The id the app knows the card by.
        season_tags: Extra tag ids that mark a Chaos season card.
        issues: Unresolved placeholders are reported here, unless the description is overridden.
        overrides: The target's overrides.

    Returns:
        The entry, before overrides.
    """
    is_monster = shard == MONSTER_SHARD
    category = "monster" if is_monster else "neutral"
    tags = [category]
    if season_tags & set(parse_list(row.get("link_extra_tag_id"))):
        tags.append("season")
    if row.get("sort") == TABOO_SORT:
        tags.append("forbidden")

    resolution = ctx.resolver.card_description(row["id"])
    issues.extend(overrides.unresolved(output_id, f"{row['id']} ({output_id})", resolution.unresolved, "description"))
    classes = class_names(ctx, row.get("ownable_link_base_class_define_id"))
    entry = {
        "id": output_id,
        "name": ctx.text(ctx.client.text(row.get("name")) or output_id, sentences=False),
        "cost": parse_cost(row.get("cost")),
        "card_type": card_type(ctx, row.get("card_category")),
        "category": category,
        "tags": tags,
        "effect_tags": ctx.resolver.talent_tags(row),
        "description": ctx.text(resolution.text),
        "restrictions": None if is_monster else restrictions(classes),
        "allowed_classes": classes,
        "image_path": image_path(shard, output_id),
    }
    # Monster cards are priced by rarity in the deck builder. Neutral cards all cost the same, so they leave it out.
    if is_monster:
        entry["rarity"] = RARITIES.get(row.get("rarity", ""))
        if entry["rarity"] is None:
            issues.append(Issue("error", f"{NAME}: {row['id']} ({output_id}) has an unknown rarity {row.get('rarity')}"))
    return entry


def image_path(shard: str, output_id: str) -> str:
    """
    Where a pool card's art lives, relative to the deck builder data folder.

    Args:
        shard: The card shard the row came from, such as "public".
        output_id: The id the app knows the card by.

    Returns:
        Such as "neutral-cards/monster/m_0001.webp".
    """
    category = "monster" if shard == MONSTER_SHARD else "neutral"
    return f"{IMAGE_DIR.as_posix()}/{category}/{output_id}.webp"


def restrictions(classes: list[str]) -> str:
    """
    The class restriction line shown under a neutral card.

    Args:
        classes: The classes that may use the card. Empty means any class.

    Returns:
        Such as "Ranger, Hunter only" or "No Class restrictions".
    """
    return f"{', '.join(classes)} only" if classes else "No Class restrictions"


def sort_key(card: dict) -> tuple:
    """
    The output order: neutral cards before monster cards, then by name, then by id.

    Args:
        card: An output entry.

    Returns:
        The sort key.
    """
    return (card["category"] == "monster", card["name"].casefold(), card["id"])


def _season_tags(ctx: Context) -> set[str]:
    """
    Extra tag ids that mark a card as belonging to a Chaos season.

    Args:
        ctx: The run context.

    Returns:
        Such as {"ds01", "ds02", "ca_ds01"}. Season ban tags are a different type, so they are not included.
    """
    return {row["id"] for row in ctx.client.rows(EXTRA_TAG_TABLE) if row.get("type") == SEASON_TAG_TYPE}


def parse_cost(raw: str | None) -> int | None:
    """
    A card's cost.

    Args:
        raw: The client cell.

    Returns:
        The cost, -1 for an X cost, or None when the client stores something that is not a number.
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
