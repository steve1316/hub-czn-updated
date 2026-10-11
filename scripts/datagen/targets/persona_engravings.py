"""
The Persona card's engravings, the Lux and Umbra effects a Persona card can be given in its two slots.

Each engraving is one row of the client's `eidolon_card_reward` table: the card type and classes it applies to, the cost
and traits it adds, and a description template. Saved decks store engraving ids, so the `pe_*` ids the hand-written file
used are pinned through the `_ids` map in the overrides file. An engraving new to the app takes its client id.
"""

from __future__ import annotations

from pathlib import Path

from scripts.datagen.art import wanted, webp
from scripts.datagen.client import parse_list
from scripts.datagen.naming import card_type, class_names, legacy_ids
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes

NAME = "persona_engravings"
OFFLINE = True

OUTPUT_PATH = Path("src/pages/deck-builder/data/deck-builder-persona-engravings.json")
DATA_DIR = Path("src/pages/deck-builder/data")
IMAGE_DIR = Path("persona")

REWARD_TABLE = "eidolon_card_define@eidolon_card_reward.json"
SLOT_INFO_TABLE = "eidolon_card_define@eidolon_card_slot_info.json"
SLOT_TYPE_TABLE = "eidolon_card_define@eidolon_slot_type_define.json"
ILLUSTRATION_TABLE = "eidolon_card_define@eidolon_card_illust_comb.json"

# The deck builder shows one picture per slot combination, and the existing art is the Skill card's. Kept at full size.
IMAGE_CATEGORY = "CARD_SKILL"
IMAGE_QUALITY = 90

# How a slot's cost change reads, by the client's math sign.
COST_SIGNS = {"MATHSIGN_ADD": "+", "MATHSIGN_SUB": "-"}

NO_SLOT = "none"

# The shared card pool's target, whose pinned ids give the Persona card its id.
NEUTRAL_CARDS_TARGET = "neutral_cards"


def build(ctx: Context) -> TargetResult:
    """
    Generate the engravings file and any missing slot-combination art.

    Args:
        ctx: The run context.

    Returns:
        The JSON file, the art to add, a summary, and any unresolved placeholders or invalid overrides.
    """
    overrides = ctx.overrides(NAME)
    pinned = legacy_ids(overrides)
    issues: list[Issue] = []
    slot_types = {row["id"]: row for row in ctx.client.rows(SLOT_TYPE_TABLE)}

    generated: dict[str, dict] = {}
    seen: set[str] = set()
    for row in ctx.client.rows(REWARD_TABLE):
        if not overrides.keeps(row["id"]):
            continue
        engraving_id = pinned.get(row["id"], row["id"])
        entry = engraving(ctx, row, engraving_id, slot_types, overrides, issues)
        generated[entry["engraving_id"]] = entry
        seen.add(row["id"])
    for client_id in sorted(set(pinned) - seen):
        issues.append(Issue("error", f"{NAME}: pinned id {pinned[client_id]} points at {client_id}, which is not a kept engraving in the client"))

    issues.extend(overrides.validate(generated))
    pinned_ids = set(pinned.values())
    engravings = sorted(overrides.apply(generated).values(), key=lambda item: (item["engraving_id"] not in pinned_ids, item["engraving_id"]))

    images, new_files = slot_images(ctx, slot_types, issues)
    card = persona_card(ctx, images)
    card["engravings"] = engravings
    summary = f"{len(engravings)} engravings, {len(new_files)} image(s) to add"
    return TargetResult({OUTPUT_PATH: json_bytes([card])}, summary, issues, new_files=new_files)


def engraving(ctx: Context, row: dict, engraving_id: str, slot_types: dict[str, dict], overrides: Overrides, issues: list[Issue]) -> dict:
    """
    One engraving in the output's format.

    Args:
        ctx: The run context.
        row: The `eidolon_card_reward` row.
        engraving_id: The id the app knows the engraving by.
        slot_types: Slot type id -> its row, for the Lux / Umbra name.
        overrides: The target's overrides. An overridden description silences unresolved placeholders.
        issues: Unresolved placeholders are reported here.

    Returns:
        The entry, before overrides.
    """
    resolution = ctx.resolver.resolve(ctx.client.text(row.get("desc")) or "", parse_list(row.get("link_skill_eff_id")))
    issues.extend(overrides.unresolved(engraving_id, f"{row['id']} ({engraving_id})", resolution.unresolved, "description"))
    slot_type = slot_types.get(row.get("link_eidolon_slot_type_define_id"), {})
    categories = parse_list(row.get("target_card_category"))
    return {
        "engraving_id": engraving_id,
        "eidolon": ctx.client.text(slot_type.get("name")) or slot_type.get("slot_type", "").capitalize(),
        "card_type": card_type(ctx, categories[0] if categories else None),
        "modifiers": modifiers(ctx, row),
        "allowed_classes": class_names(ctx, row.get("target_link_base_class_define_id")),
        "tags": [],
        # Every line break in an engraving template wraps one sentence, so the lines are joined with spaces.
        "description": ctx.text(resolution.text.replace("\n", " "), sentences=False),
    }


def modifiers(ctx: Context, row: dict) -> list[str]:
    """
    What an engraving changes on the card it is put on, besides its effect.

    Args:
        ctx: The run context.
        row: The `eidolon_card_reward` row.

    Returns:
        A cost change such as "Cost +1" first, then the traits it adds, such as "Haste".
    """
    result = []
    sign = COST_SIGNS.get(row.get("slot_add_cost_mathsign", ""))
    cost = row.get("slot_add_cost", "0")
    if sign and cost not in ("", "0"):
        result.append(f"Cost {sign}{cost}")
    for talent in parse_list(row.get("slot_add_card_talent")):
        title = ctx.resolver.talent_title(talent) if talent != "TALENT_NONE" else None
        if title:
            result.append(title)
    return result


def slot_images(ctx: Context, slot_types: dict[str, dict], issues: list[Issue]) -> tuple[dict[str, str], dict[Path, bytes]]:
    """
    The Persona card's picture for each slot combination, plus the plain slot icons.

    Args:
        ctx: The run context.
        slot_types: Slot type id -> its row, in the client's order.
        issues: Missing art is reported here.

    Returns:
        The image key -> path map in display order, and the images to add.
    """
    order = list(slot_types)
    short = {type_id: row.get("slot_type", type_id).lower() for type_id, row in slot_types.items()}
    paths: dict[str, str] = {}
    for type_id in order:
        paths[short[type_id]] = f"{IMAGE_DIR.as_posix()}/{short[type_id]}.webp"

    combos: dict[str, str] = {}
    for row in ctx.client.rows(ILLUSTRATION_TABLE):
        if row.get("card_category") != IMAGE_CATEGORY:
            continue
        key = combination_key(row.get("slot_type_0"), row.get("slot_type_1"), short, order)
        if key:
            combos.setdefault(key, row.get("change_to_sct_name", ""))
    for key in sorted(combos, key=lambda name: combination_order(name, [short[type_id] for type_id in order])):
        paths[key] = f"{IMAGE_DIR.as_posix()}/{key}.webp"

    new_files: dict[Path, bytes] = {}
    for key, path in paths.items():
        target = DATA_DIR / path
        if not wanted(ctx, target):
            continue
        source = ctx.client.root / "card_illustration" / f"{combos.get(key, '')}.png"
        if key in combos and source.is_file():
            new_files[target] = webp(source, quality=IMAGE_QUALITY)
        elif not (REPO_ROOT / target).exists():
            # The plain slot icons are UI sprites the extraction does not include, so they are only reported when missing.
            issues.append(Issue("warning", f"{NAME}: no art in the client for the '{key}' Persona image ({target.as_posix()})"))
    return paths, new_files


def combination_key(first: str | None, second: str | None, short: dict[str, str], order: list[str]) -> str | None:
    """
    The image key of one slot combination.

    Args:
        first: The first slot's type id.
        second: The second slot's type id, or "none".
        short: Slot type id -> short name, such as "lux".
        order: Slot type ids in the client's order, so "lux_and_umbra" and "umbra_and_lux" are one key.

    Returns:
        Such as "half_lux", "all_umbra" or "lux_and_umbra". None when a slot type is unknown.
    """
    if first not in short or (second != NO_SLOT and second not in short):
        return None
    if second == NO_SLOT:
        return f"half_{short[first]}"
    if first == second:
        return f"all_{short[first]}"
    pair = sorted((first, second), key=order.index)
    return f"{short[pair[0]]}_and_{short[pair[1]]}"


def combination_order(key: str, names: list[str]) -> tuple:
    """
    The display order of combination keys: one slot filled first, then both, following the slot type order.

    Args:
        key: Such as "half_lux" or "lux_and_umbra".
        names: Short slot type names in the client's order.

    Returns:
        The sort key.
    """
    if key.startswith("half_"):
        return (0, names.index(key[5:]), 0)
    if key.startswith("all_"):
        return (1, names.index(key[4:]), names.index(key[4:]))
    first, second = key.split("_and_")
    return (1, names.index(first), names.index(second))


def persona_card(ctx: Context, images: dict[str, str]) -> dict:
    """
    The Persona card the engravings belong to, without its engravings.

    Args:
        ctx: The run context.
        images: Image key -> path.

    Returns:
        The card. Its id is the shared pool's id for the first Persona card, so the two files agree.
    """
    slot_info = ctx.client.rows(SLOT_INFO_TABLE)
    client_id = slot_info[0]["link_card_id"] if slot_info else "persona"
    card_id = legacy_ids(ctx.overrides(NEUTRAL_CARDS_TARGET)).get(client_id, client_id)
    first_icon = next(iter(images.values()), None)
    return {
        "id": card_id,
        "image_id": card_id,
        "name": ctx.resolver.card_name(client_id) or "Persona",
        "category": "persona",
        "image_type": "persona",
        "image_path": first_icon,
        "persona_image_paths": images,
    }
