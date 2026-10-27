"""
The Encyclopedia's card list: every card in the game's own card archive, grouped the way the archive groups them.

The archive lists combatant cards (starting and epiphany cards, plus each one's epiphanies), neutral cards, the cards of
each Chaos season, monster cards, status ailments and curses. Epiphanies fold into their base card, and each combatant's
ego skill is added, since the archive leaves it out. Art the deck builder already ships is reused, the rest is added.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.datagen import epiphany, roster
from scripts.datagen.art import CLIENT_ART_QUALITY, wanted, webp
from scripts.datagen.client import parse_list
from scripts.datagen.naming import card_type, legacy_ids, slug
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import Context, TargetResult, json_bytes
from scripts.datagen.targets import card_art, neutral_cards

NAME = "encyclopedia_cards"
OFFLINE = True

PAGES_DIR = Path("src/pages")
OUTPUT_PATH = PAGES_DIR / "encyclopedia/data/encyclopedia-cards.json"
# Image paths in the output are relative to `PAGES_DIR`, so the page can match them against its image globs.
ART_DIR = Path("encyclopedia/data/card-art")
DECK_BUILDER_DIR = Path("deck-builder/data")

# The archive tables after the combatant one, in the order the Encyclopedia lists them.
SHARED_TABLES = ("public", "season", "monster", "etc")

# Season 5's cards live in a shard of their own, outside the `card(*)` shards the client loads as cards.
EXTRA_CARD_SHARDS = ("memory_grade_define@card.json",)

# The combatant sub-category that lists epiphany variants, which fold into their base card instead.
EPIPHANY_SUB_CATEGORY = "combatant_uni_spark"
# The sub-category every neutral card is in, besides its classes.
ALL_CLASSES_SUB_CATEGORY = "public_all"

SEASON_KINDS = {"neutral": "neutral", "season_power": "power", "system": "system"}
ETC_GROUPS = {"etc_abnorm": "ailment", "etc_curse": "curse"}

_COMBATANT_CARD = re.compile(r"^c_(\d+)_(srt|uni)\d+$")
_SEASON = re.compile(r"^season_s(\d+)$")


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Build


def build(ctx: Context) -> TargetResult:
    """
    Generate the Encyclopedia's card list and any missing card art.

    Args:
        ctx: The run context.

    Returns:
        The JSON file, the art to add, a summary, and any missing cards or unresolved placeholders.
    """
    builder = _Builder(ctx)
    builder.add_combatants()
    for table in SHARED_TABLES:
        for archive in ctx.client.rows(f"archive_card({table})@archive_card.json"):
            builder.add_shared(table, archive)

    seasons = sorted({card["season"] for card in builder.cards if "season" in card})
    document = {
        "seasons": [{"number": number, "title": ctx.client.text(f"archive_card@title@season_s{number}") or f"Season {number}"} for number in seasons],
        "characters": [{"id": res_id, "name": character["name"]} for res_id, character in roster.by_name() if res_id in builder.characters],
        "cards": builder.cards,
    }
    summary = f"{len(builder.cards)} cards, {len(builder.new_files)} image(s) to add"
    return TargetResult({OUTPUT_PATH: json_bytes(document)}, summary, builder.issues, new_files=builder.new_files)


class _Builder:
    """Collects the output cards, the art to add and the issues found along the way."""

    def __init__(self, ctx: Context):
        """
        Args:
            ctx: The run context.
        """
        self.ctx = ctx
        # Output cards, in archive order.
        self.cards: list[dict] = []
        # Combatants with at least one card in the output.
        self.characters: set[int] = set()
        # Images to add, repo-relative path -> WebP bytes.
        self.new_files: dict[Path, bytes] = {}
        # Problems found while building.
        self.issues: list[Issue] = []
        self._extra_rows = {row["id"]: row for shard in EXTRA_CARD_SHARDS for row in ctx.client.rows(shard) if "id" in row}
        self._pool_images = _pool_images(ctx)
        self._folders = card_art.existing_folders()

    def add_combatants(self) -> None:
        """Add each shipped combatant's starting and epiphany cards, then its ego skill, in roster order."""
        by_character: dict[int, list[tuple[str, str]]] = {}
        for archive in self.ctx.client.rows("archive_card(combatant)@archive_card.json"):
            if archive.get("link_archive_card_sub_category_id") == EPIPHANY_SUB_CATEGORY:
                continue
            card_id = archive.get("link_card_id", "")
            match = _COMBATANT_CARD.match(card_id)
            if match is None:
                self.issues.append(Issue("warning", f"{NAME}: {card_id} is not a starting or epiphany card id, so it is left out"))
                continue
            kind = "starting" if match.group(2) == "srt" else "epiphany"
            by_character.setdefault(int(match.group(1)), []).append((card_id, kind))

        combatants = self.ctx.client.by_id(card_art.COMBATANT_TABLE)
        for res_id, character in roster.by_name():
            ego = combatants.get(str(res_id), {}).get("collapse_skill_link_card_id")
            folder = self._folders.get(res_id) or slug(character["name"])
            for card_id, kind in by_character.get(res_id, []) + ([(ego, "ego")] if ego else []):
                fields = {"group": "combatant", "kind": kind, "character_id": res_id}
                image = (DECK_BUILDER_DIR / "combatants" / folder / f"{card_id}.webp").as_posix()
                if self._add(card_id, fields, image):
                    self.characters.add(res_id)

    def add_shared(self, table: str, archive: dict) -> None:
        """
        Add one card from a shared archive table.

        Args:
            table: The table, such as "season".
            archive: The archive row.
        """
        sub_categories = parse_list(archive.get("link_archive_card_sub_category_id"))
        if table == "public":
            classes = [self._title(sub) for sub in sub_categories if sub != ALL_CLASSES_SUB_CATEGORY]
            fields = {"group": "neutral", "kind": "neutral", "classes": classes}
        elif table == "season":
            season = next((int(match.group(1)) for sub in sub_categories if (match := _SEASON.match(sub))), 0)
            kind = SEASON_KINDS.get(archive.get("link_archive_card_sort_type_id", ""), "neutral")
            fields = {"group": "season", "kind": kind, "season": season}
        elif table == "monster":
            fields = {"group": "monster", "kind": "monster", "faction": self._title(sub_categories[0]) if sub_categories else None}
        else:
            group = next((ETC_GROUPS[sub] for sub in sub_categories if sub in ETC_GROUPS), "curse")
            fields = {"group": group, "kind": group}
        self._add(archive.get("link_card_id", ""), fields, None)

    def _add(self, card_id: str, fields: dict, image: str | None) -> bool:
        """
        Add one card to the output.

        Args:
            card_id: The client card id.
            fields: The grouping fields, such as `group` and `kind`.
            image: The art path relative to `PAGES_DIR`, or None to reuse the deck builder's pool art or add the card's own.

        Returns:
            Whether the card was added. A card missing from the client, or with no name, is left out with a warning.
        """
        row = self.ctx.client.cards.get(card_id) or self._extra_rows.get(card_id)
        name = self.ctx.client.text(row.get("name")) if row else None
        if not name:
            self.issues.append(Issue("warning", f"{NAME}: {card_id} is in the card archive but has no card or name in the client"))
            return False
        resolution = self.ctx.resolver.describe(row)
        if resolution.unresolved:
            self.issues.append(Issue("warning", f"{NAME}: {card_id} has unresolved placeholders {resolution.unresolved}"))
        card = {
            "id": card_id,
            "name": self.ctx.text(name, sentences=False),
            "cost": neutral_cards.parse_cost(row.get("cost")),
            "card_type": card_type(self.ctx, row.get("card_category")),
            # A card with no text, such as Wound, still shows its traits.
            "description": self.ctx.text(resolution.text) or " ".join(f"[{tag}]" for tag in self.ctx.resolver.talent_tags(row)),
            **fields,
            "image": image or self._shared_image(row),
        }
        found = epiphany.variants(self.ctx, card_id)[1:]
        if found:
            card["epiphanies"] = [{"level": v.level, "name": v.name, "cost": v.cost, "description": v.text} for v in found]
        self.cards.append(card)
        return True

    def _shared_image(self, row: dict) -> str | None:
        """
        The art for a card outside the combatant folders: the deck builder's pool art when it has the card, else its own.

        Args:
            row: The card row.

        Returns:
            The path relative to `PAGES_DIR`, or None when the client has no illustration for the card.
        """
        if row["id"] in self._pool_images:
            return self._pool_images[row["id"]]
        source = self.ctx.client.illustration(row, columns=("sct_name",))
        if source is None:
            self.issues.append(Issue("warning", f"{NAME}: no illustration in the client for {row['id']} ({row.get('sct_name')}.png)"))
            return None
        # Cards that share an illustration, such as the four grades of a Season 5 memory, share one image.
        image = ART_DIR / f"{source.stem}.webp"
        if wanted(self.ctx, PAGES_DIR / image) and PAGES_DIR / image not in self.new_files:
            self.new_files[PAGES_DIR / image] = webp(source, quality=CLIENT_ART_QUALITY)
        return image.as_posix()

    def _title(self, sub_category: str) -> str:
        """
        An archive sub-category as the game names it, such as "Nihilum Faction".

        Args:
            sub_category: The sub-category id.

        Returns:
            The game's title, or the id when the client has none.
        """
        return self.ctx.client.text(f"archive_card@title@{sub_category}") or sub_category


def _pool_images(ctx: Context) -> dict[str, str]:
    """
    The deck builder's art for its shared card pool.

    Args:
        ctx: The run context.

    Returns:
        client card id -> image path relative to `PAGES_DIR`.
    """
    overrides = ctx.overrides(neutral_cards.NAME)
    pinned = legacy_ids(overrides)
    rows = neutral_cards.select_rows(ctx, pinned, overrides, [])
    return {row["id"]: (DECK_BUILDER_DIR / neutral_cards.image_path(shard, pinned.get(row["id"], row["id"]))).as_posix() for shard, row in rows}
