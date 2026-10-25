"""
Equipment for the deck builder and the encyclopedia: every weapon, armor and accessory a player can find in a run.

Rows come from the client's relic tables, kept to the three equipment slots. Descriptions are the client's own templates.
The relic-only value tokens are filled in here, then the shared resolver handles the rest of the markup. The item icons
are not in the extracted client, so `image_path` comes from the overrides file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.datagen.client import parse_list
from scripts.datagen.naming import RARITIES
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes
from scripts.datagen.templates import format_number

NAME = "items"
OFFLINE = True

ITEMS_PATH = Path("src/pages/deck-builder/data/deck-builder-items.json")

# `image_path` values are relative to this folder.
IMAGES_ROOT = Path("src/pages/deck-builder/data")

# Relic tables that hold equipment, in output order. The `relic(assault)` table only holds `_ca` copies for another mode.
RELIC_TABLES = ("relic@relic.json", "relic(disaster)@relic.json")

SLOTS = {"EQUIP_WEAPON": "Weapon", "EQUIP_ARMOR": "Armor", "EQUIP_ACC": "Accessory"}

# `#rev_N_M#` shows the term value of the relic's Nth linked status, its `s1_cs_value[N]`. M only names the status effect
# the value feeds, so it does not change the number shown.
_STATUS_VALUE = re.compile(r"#rev_(\d+)_\d+#")

# `#nbev_N#` shows the value of the relic's Nth linked passive effect, its `s1_nb_eff_value[N]`.
_PASSIVE_VALUE = re.compile(r"#nbev_(\d+)#")


def build(ctx: Context) -> TargetResult:
    """
    Generate the items file.

    Args:
        ctx: The run context.

    Returns:
        The file, a summary, and any unresolved placeholders, unknown rarities, missing images or invalid overrides as issues.
    """
    overrides = ctx.overrides(NAME)
    issues: list[Issue] = []
    generated: dict[str, dict] = {}
    for table in RELIC_TABLES:
        for row in ctx.client.rows(table):
            slot = SLOTS.get(row.get("relic_type", ""))
            item_id = row.get("id")
            if slot is None or not item_id or not overrides.keeps(item_id):
                continue
            generated[item_id] = _item(ctx, row, slot, overrides, issues)

    issues.extend(overrides.validate(generated))
    items = list(overrides.apply(generated).values())
    for item in items:
        if item["image_path"] and not (REPO_ROOT / IMAGES_ROOT / item["image_path"]).is_file():
            issues.append(Issue("error", f"{NAME}: {item['id']} points at a missing image {item['image_path']}"))
    return TargetResult({ITEMS_PATH: json_bytes(items)}, _summary(items), issues)


def _item(ctx: Context, row: dict, slot: str, overrides: Overrides, issues: list[Issue]) -> dict:
    """
    One equipment row in the items file's format, before overrides.

    Args:
        ctx: The run context.
        row: The relic row.
        slot: The display slot, such as "Weapon".
        overrides: The target's overrides. Any entry for this id silences unresolved placeholders.
        issues: Problems with the row are reported here.

    Returns:
        The item, with an empty `image_path` and an English-only description.
    """
    item_id = row["id"]
    name = ctx.client.text(row.get("name"))
    if not name:
        issues.append(Issue("error", f"{NAME}: {item_id} has no name text"))
    rarity = RARITIES.get(row.get("rarity", ""))
    if rarity is None:
        issues.append(Issue("error", f"{NAME}: {item_id} has an unknown rarity {row.get('rarity')}"))

    template = ctx.client.text(row.get("s1_description")) or ""
    resolution = ctx.resolver.resolve(fill_relic_values(template, row), [])
    issues.extend(overrides.unresolved(item_id, item_id, resolution.unresolved))

    return {
        "id": item_id,
        "name": ctx.text(name or item_id, sentences=False),
        "rarity": rarity or "Rare",
        "slot": slot,
        "tags": [],
        "description": {"en": ctx.text(resolution.text)},
        "image_path": "",
    }


def fill_relic_values(template: str, row: dict) -> str:
    """
    Fill in the value tokens that only relic descriptions use, from the relic row's base tier.

    Args:
        template: The raw description template.
        row: The relic row. Its `s1_cs_value` and `s1_nb_eff_value` lists hold the values.

    Returns:
        The template with `#rev_N_M#` and `#nbev_N#` replaced. A token whose index is out of range is left as written, so
        the shared resolver reports it as unresolved.
    """
    status_values = parse_list(row.get("s1_cs_value"))
    passive_values = parse_list(row.get("s1_nb_eff_value"))
    template = _STATUS_VALUE.sub(lambda match: _value_at(status_values, match), template)
    return _PASSIVE_VALUE.sub(lambda match: _value_at(passive_values, match), template)


def _value_at(values: list[str], match: re.Match) -> str:
    """
    The value a matched token points at.

    Args:
        values: The row's value list for that token kind.
        match: The token, whose first group is the index into `values`.

    Returns:
        The formatted value, or the token unchanged when the index is out of range.
    """
    index = int(match.group(1))
    return format_number(values[index]) if index < len(values) else match.group(0)


def _summary(items: list[dict]) -> str:
    """
    One line describing the generated items against the file on disk.

    Args:
        items: The final items.

    Returns:
        The item count, how many ids were added or dropped, and how many items have an image.
    """
    path = REPO_ROOT / ITEMS_PATH
    current = {entry.get("id") for entry in json.loads(path.read_text(encoding="utf-8"))} if path.is_file() else set()
    ids = {item["id"] for item in items}
    with_images = sum(1 for item in items if item["image_path"])
    return f"{len(items)} items (+{len(ids - current)} new, -{len(current - ids)} dropped), {with_images} with images"
