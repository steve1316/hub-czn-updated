"""
The deck builder's per-character card lists and their epiphany variants.

Each combatant row in the client names its four starting cards, four epiphany cards and its ego skill, and every
epiphany card has up to five variants listed in the `card_r_spark` tables. Descriptions are the client's own templates,
resolved and tidied, so the numbers always match the current game.
"""

from __future__ import annotations

from pathlib import Path

from scripts.datagen import roster
from scripts.datagen.epiphany import epiphany_name
from scripts.datagen.naming import CARD_TYPES
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import Context, TargetResult, json_bytes

NAME = "deck_builder"
OFFLINE = True

CARDS_PATH = Path("api/data/deck_builder_cards.json")
VARIANTS_PATH = Path("api/data/deck_builder_epiphany_variants.json")

COMBATANT_TABLE = "char_base@char_combatant.json"


def build(ctx: Context) -> TargetResult:
    """
    Generate both deck builder files.

    Args:
        ctx: The run context.

    Returns:
        The two files, a summary, and any unresolved placeholders or invalid overrides as issues.
    """
    combatants = ctx.client.by_id(COMBATANT_TABLE)
    overrides = ctx.overrides(NAME)
    issues: list[Issue] = []
    generated: dict[str, dict] = {}

    def describe(card_id: str, base_card_id: str | None = None) -> str:
        resolution = ctx.resolver.card_description(card_id, base_card_id=base_card_id)
        text = ctx.text(resolution.text)
        generated[card_id] = {"description": text}
        issues.extend(overrides.unresolved(card_id, card_id, resolution.unresolved))
        return overrides.value(card_id, "description", text)

    manifest: dict[str, dict] = {}
    variants: dict[str, dict] = {}
    missing = []
    for res_id, character in roster.by_name():
        row = combatants.get(str(res_id))
        if row is None:
            missing.append(character["name"])
            continue
        starting = [row.get(f"start_{n}_link_card_id") for n in range(1, 5)]
        epiphany = [row.get(f"spark_card_{n}_link_card_id") for n in range(1, 5)]
        ego = row.get("collapse_skill_link_card_id")
        manifest[str(res_id)] = {
            "character_name": character["name"],
            "starting_cards": [{"card_id": card_id, "description": describe(card_id)} for card_id in starting if _real(card_id)],
            "epiphany_cards": [{"card_id": card_id, "description": describe(card_id)} for card_id in epiphany if _real(card_id)],
            "ego_skill": {"card_id": ego, "description": describe(ego)} if _real(ego) else None,
        }
        for base in starting + epiphany:
            if _real(base):
                group = _variant_group(ctx, res_id, character["name"], base, describe)
                if group:
                    variants[base] = group

    issues.extend(overrides.validate(generated))
    if missing:
        issues.append(Issue("warning", f"{NAME}: no combatant row in the client for {', '.join(missing)}"))
    summary = f"{len(manifest)} characters, {len(variants)} cards with epiphany variants"
    return TargetResult({CARDS_PATH: json_bytes(manifest), VARIANTS_PATH: json_bytes(variants)}, summary, issues)


def _variant_group(ctx: Context, res_id: int, character_name: str, base: str, describe) -> dict | None:
    """
    One base card's epiphany variants.

    Args:
        ctx: The run context.
        res_id: The owning combatant.
        character_name: Its display name.
        base: The base card id.
        describe: Resolves and records a card's description.

    Returns:
        The group in the variants file's format, or None when the card has no variants.
    """
    levels = ctx.client.variants_by_base.get(base)
    if not levels:
        return None
    base_name = ctx.resolver.card_name(base) or base
    entries = []
    for level, card_id in levels:
        card = ctx.client.cards.get(card_id, {})
        entries.append({
            "variant_id": f"{base}_epiphany_{level}",
            "level": level,
            "name": epiphany_name(base_name, level, ctx.resolver.card_name(card_id)),
            "cost": int(card.get("cost", 0) or 0),
            "card_type": CARD_TYPES.get(card.get("card_category", ""), "Skill"),
            "tags": ctx.resolver.talent_tags(card),
            "description": describe(card_id, base),
        })
    return {"character_id": res_id, "character_name": character_name, "base_card_id": base, "base_card_name": base_name, "variants": entries}


def _real(card_id: str | None) -> bool:
    """Whether a card cell holds a card id rather than an empty placeholder."""
    return bool(card_id) and card_id != "none"
