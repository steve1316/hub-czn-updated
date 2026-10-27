"""
The Encyclopedia's card list: every card in the game's own card archive, grouped the way the archive groups them.

The archive lists combatant cards (starting and epiphany cards, plus each one's epiphanies), neutral cards, the cards of
each Chaos season, monster cards, status ailments and curses. Epiphanies fold into their base card, and each combatant's
ego skill is added, since the archive leaves it out. Art the deck builder already ships is reused, the rest is added.

The keywords and card names the game marks in card text are listed too, with their definitions and the cards they name,
so the page can link them.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.client_db import REPO_ROOT
from scripts.datagen import epiphany, roster
from scripts.datagen.art import CLIENT_ART_QUALITY, wanted, webp
from scripts.datagen.client import parse_list
from scripts.datagen.naming import card_type, legacy_ids, slug
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import Context, TargetResult, json_bytes
from scripts.datagen.targets import card_art, glossary, neutral_cards

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
_COMBATANT_ID = re.compile(r"^c_(\d+)_")
_SEASON = re.compile(r"^season_s(\d+)$")

# Card text markers: `$Draw$` or `$Retain#1$` for a keyword, `^TRIGGER_EXHAUST^` for a trigger, `^card@id^` or an
# underlined name for a card.
_KEYWORD = re.compile(r"\$([^$#]+)(?:#\d+)?\$")
_TRIGGER = re.compile(r"\^([A-Z][A-Z0-9_]+)\^")
_CARD_ID = re.compile(r"\^card@([A-Za-z0-9_]+)\^")
_UNDERLINED = re.compile(r"<u>(.*?)</u>")
_TAG = re.compile(r"<[^>]*>")
# A card's family is its id up to the second "_", such as "c_1055" or "card_ab".
_FAMILY = re.compile(r"^[^_]+_[^_]+")
# A battle-only value left in a definition, such as `#tv#`, and a sentence that is only such a value.
_PLACEHOLDER = re.compile(r"#[A-Za-z0-9_]+#")
_PLACEHOLDER_SENTENCE = re.compile(r"\s*#[A-Za-z0-9_]+#\.")
# The endings `_stem` drops, so "Fixed Heal" meets the tooltip titled "Fixed Healing".
_STEM_ENDING = re.compile(r"(ing|ed|s)$")
_SPACES = re.compile(r"\s+")
# Keywords shorter than this, such as "X", are left unlinked.
MIN_KEYWORD_LENGTH = 2


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Build


def _stem(name: str) -> str:
    """
    A keyword name reduced to its stem. The game matches card keywords to tooltips by their Korean text, which the client
    export lacks, and the English keyword often differs from the tooltip title by an ending, such as "Ego Point" and "Ego Points".

    Args:
        name: The keyword or tooltip title.

    Returns:
        The lower-cased name without a trailing colon, "(s)" or a final "ing", "ed" or "s".
    """
    return _STEM_ENDING.sub("", name.lower().replace("(s)", "").strip().rstrip(":"))


def _name_key(name: str) -> str:
    """
    A card name without its spaces, since card text sometimes writes "Softie ★" as "Softie★".

    Args:
        name: The card name.

    Returns:
        The name with every space removed.
    """
    return _SPACES.sub("", name)


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
    listed = {card["id"] for card in builder.cards}
    card_links = builder.card_links(listed)
    keywords = sorted((name, definition) for name, definition in builder.keywords.items() if definition)
    document = {
        "seasons": [{"number": number, "title": ctx.client.text(f"archive_card@title@season_s{number}") or f"Season {number}"} for number in seasons],
        "characters": [{"id": res_id, "name": character["name"]} for res_id, character in roster.by_name() if res_id in builder.characters],
        "cards": builder.cards,
        "keywords": [{"name": name, "definition": definition} for name, definition in keywords],
        "card_links": [{"name": name, "id": card_id} for name, card_id in sorted(card_links.items())],
        "linked_cards": [builder.linked_card(card_id) for card_id in sorted(set(card_links.values()) - listed)],
    }
    summary = f"{len(builder.cards)} cards, {len(keywords)} keywords, {len(card_links)} card links, {len(builder.new_files)} image(s) to add"
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
        # Keyword name -> its definition, or None when the client has none. Trigger names keep their colon.
        self.keywords: dict[str, str | None] = {}
        self._extra_rows = {row["id"]: row for shard in EXTRA_CARD_SHARDS for row in ctx.client.rows(shard) if "id" in row}
        self._pool_images = _pool_images(ctx)
        self._folders = card_art.existing_folders()
        # Tooltip title -> its tooltip ids, in id order, and the same keyed by `_stem` for keywords that miss by an ending.
        self._tooltips_by_title: dict[str, list[str]] = {}
        self._tooltips_by_stem: dict[str, list[str]] = {}
        for tooltip_id in sorted(ctx.client.tooltips):
            title = ctx.client.text(ctx.client.tooltips[tooltip_id].get("title"))
            if title:
                self._tooltips_by_title.setdefault(title, []).append(tooltip_id)
                self._tooltips_by_stem.setdefault(_stem(title), []).append(tooltip_id)
        # Card references found in card text, as (card id, None) or (None, card name), with the referring card row.
        self._references: list[tuple[str | None, str | None, dict]] = []

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
        row = self._row(card_id)
        if not row or not self.ctx.client.text(row.get("name")):
            self.issues.append(Issue("warning", f"{NAME}: {card_id} is in the card archive but has no card or name in the client"))
            return False
        card = {**self._card(row), **fields, "image": image or self._shared_image(row)}
        found = epiphany.variants(self.ctx, card_id)[1:]
        if found:
            card["epiphanies"] = [{"level": v.level, "name": v.name, "cost": v.cost, "description": v.text} for v in found]
        self.cards.append(card)
        base_template = self.ctx.client.text(row.get("desc")) or ""
        for marked in [row] + [self.ctx.client.cards[v.card_id] for v in found]:
            self._collect_marks(marked, self.ctx.client.text(marked.get("desc")) or base_template, row)
        return True

    def card_links(self, listed: set[str]) -> dict[str, str]:
        """
        The cards named in card text, by the name the text shows.

        Args:
            listed: The ids of the cards in the list.

        Returns:
            card name -> card id. A name shared by cards of more than one family is left out, since it is unclear which one
            the text means, unless one family is the referring card's own. A name the text writes without its spaces or as a
            plural, such as "Softie★" or "Anchor Shots", still counts. Otherwise a listed card is preferred, then one the
            referring card creates, then the first by id.
        """
        by_name: dict[str, list[str]] = {}
        for card_id in sorted([*self.ctx.client.cards, *self._extra_rows]):
            name = self.ctx.client.text(self._row(card_id).get("name"))
            if name:
                by_name.setdefault(_name_key(name), []).append(card_id)
        links: dict[str, str] = {}
        for card_id, name, referrer in self._references:
            if card_id:
                name = self.ctx.client.text(self._row(card_id).get("name")) if self._row(card_id) else None
                candidates = [card_id] if name else []
            else:
                key = _name_key(name)
                candidates = by_name.get(key) or by_name.get(key.removesuffix("s"), [])
            if len({_FAMILY.match(c).group(0) for c in candidates}) > 1:
                own = _FAMILY.match(referrer["id"]).group(0)
                candidates = [c for c in candidates if _FAMILY.match(c).group(0) == own]
            if not candidates or name in links:
                continue
            created = parse_list(referrer.get("child_link_card_id"))
            links[name] = next((c for c in candidates if c in listed), None) or next((c for c in candidates if c in created), candidates[0])
        return links

    def linked_card(self, card_id: str) -> dict:
        """
        A card named in card text but not in the list, with just what its preview shows.

        Args:
            card_id: The client card id.

        Returns:
            The card, with the deck builder's combatant art for it, else its own illustration, else the art of the card it
            was made from, such as `c_1060_uni4` for `c_1060_uni4_lbk_mut`.
        """
        row = self._row(card_id)
        match = _COMBATANT_ID.match(card_id)
        folder = self._folders.get(int(match.group(1))) if match else None
        parts = card_id.split("_")
        art = [DECK_BUILDER_DIR / "combatants" / folder / f"{'_'.join(parts[:end])}.webp" for end in range(len(parts), 2, -1)] if folder else []
        existing = [path for path in art if (REPO_ROOT / PAGES_DIR / path).is_file()]
        if art and (existing[:1] == art[:1] or not self.ctx.client.illustration(row, columns=("sct_name",))):
            image = existing[0].as_posix() if existing else None
        else:
            image = self._shared_image(row)
        return {**self._card(row), "image": image}

    def _row(self, card_id: str) -> dict | None:
        """
        A card row from the `card(*)` shards or the extra shards.

        Args:
            card_id: The client card id.

        Returns:
            The row, or None when the client has no such card.
        """
        return self.ctx.client.cards.get(card_id) or self._extra_rows.get(card_id)

    def _card(self, row: dict) -> dict:
        """
        The fields every output card has, apart from its art.

        Args:
            row: The card row, which must have a name.

        Returns:
            The id, name, cost, type and resolved description.
        """
        resolution = self.ctx.resolver.describe(row)
        if resolution.unresolved:
            self.issues.append(Issue("warning", f"{NAME}: {row['id']} has unresolved placeholders {resolution.unresolved}"))
        return {
            "id": row["id"],
            "name": self.ctx.text(self.ctx.client.text(row.get("name")), sentences=False),
            "cost": neutral_cards.parse_cost(row.get("cost")),
            "card_type": card_type(self.ctx, row.get("card_category")),
            # A card with no text, such as Wound, still shows its traits.
            "description": self.ctx.text(resolution.text) or " ".join(f"[{tag}]" for tag in self.ctx.resolver.talent_tags(row)),
        }

    def _collect_marks(self, row: dict, template: str, referrer: dict) -> None:
        """
        Note the keywords, traits and card references one card's text marks.

        Args:
            row: The card row, for its traits.
            template: Its raw text template.
            referrer: The listed card the text belongs to, whose created cards break ties between same-named cards.
        """
        for name in _KEYWORD.findall(template):
            name = name.strip()
            self._keyword(name, self._tooltips_by_title.get(name) or self._tooltips_by_stem.get(_stem(name), []))
        for trigger in _TRIGGER.findall(template):
            title = self.ctx.resolver.trigger_title(trigger)
            if title:
                self._keyword(title, [trigger])
        for talent in parse_list(row.get("talent")):
            tooltip_id = self.ctx.resolver.talent_tooltip_id(talent.strip("["))
            if tooltip_id:
                self._keyword(self.ctx.resolver.tooltip_title(tooltip_id), [tooltip_id])
        self._references += [(card_id, None, referrer) for card_id in _CARD_ID.findall(template)]
        self._references += [(None, _TAG.sub("", name).strip(), referrer) for name in _UNDERLINED.findall(template)]

    def _keyword(self, name: str, tooltip_ids: list[str]) -> None:
        """
        Add a keyword with the first definition its tooltips give, preferring one with every placeholder filled. Values
        only known in battle read "X". Lower-case keywords such as "activate" are verbs whose sense shifts, so they are skipped.

        Args:
            name: The keyword as the card text shows it.
            tooltip_ids: The tooltips that may define it, in order.
        """
        if name in self.keywords or len(name) < MIN_KEYWORD_LENGTH or "#" in name or not name[0].isupper():
            return
        found = [glossary.source_text(self.ctx, {"tooltip": tooltip_id}, self.ctx.client.constants) for tooltip_id in tooltip_ids]
        defined = [(definition, unresolved) for _, definition, unresolved in found if definition]
        definition = next((definition for definition, unresolved in defined if not unresolved), defined[0][0] if defined else None)
        self.keywords[name] = _PLACEHOLDER.sub("X", _PLACEHOLDER_SENTENCE.sub("", definition)) if definition else None

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
