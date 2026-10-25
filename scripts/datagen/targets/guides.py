"""
The Guides page, imported from the community Google Sheet ("Sproot's Nightmare").

Each character tab in the sheet becomes one guide. A tab is a free-form layout of side-by-side panels, so the importer
works from its cell grid: empty rows split it into bands, each band becomes a section, and the 6-column panels inside a
band become blocks in reading order. Text is kept as written, through the tidy pass with swear-softening. Faces become
character ids and card renders become card ids where the game's art identifies them clearly. A card is looked for among
the guide character's own cards first, then among every card in the deck builder. The rest is reported, and can be
filled in through `api/data/overrides/guides.json` keyed by tab and cell, such as "Tenebria!B11".

This target needs the network, so it only runs when named: `python -m scripts.datagen guides`.
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from dataclasses import dataclass, field
from functools import cached_property, lru_cache, partial
from pathlib import Path

from PIL import Image

from scripts.datagen import card_text, epiphany, images, roster
from scripts.datagen.epiphany import Extra
from scripts.datagen.set_names import set_line
from scripts.datagen.naming import slug
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes
from scripts.datagen.targets import card_art, neutral_cards
from scripts.datagen.sheet import EDIT_URL, HTMLVIEW_URL, TAB_URL, Cell, Fetcher, parse_grid, tabs

NAME = "guides"
OFFLINE = False

DATA_DIR = Path("src/pages/guides/data")
CONTENT_PATH = Path("src/pages/guides/guides-content.ts")
OVERRIDES_FILE = "api/data/overrides/guides.json"

SOURCE_LABEL = "Sproot's Nightmare (community sheet)"

# Panels sit side by side in blocks of 6 columns, starting at column B.
PANEL_WIDTH = 6

# A cell whose text is a rating, such as "4/5", "4.5" or "3.5/5".
_RATING = re.compile(r"^\d+(?:\.\d+)?(?:\s*/\s*\d+)?$")
# Short labels that sit side by side on one row, such as "Cycle -11 | Arpeggio Spotlight | AP -1".
_LABEL_MAX_LENGTH = 40
# Guide and section ids are cut to this length.
_SLUG_MAX_LENGTH = 48
# A section holding only these lines ("Last Edit", "10/24") is the sheet's edit date, shown as the guide's Updated badge instead.
_LAST_EDIT = re.compile(r"^(?:last edit(?:ed)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)$", re.IGNORECASE)
# A character's own cards, such as `c_1003_uni1`, whose digits are the character's res_id.
_OWN_CARD = re.compile(r"^c_(\d+)_")
# A prose line that notes one listed card or partner, such as "Tassel: BASE DAMAGE" or "Flow 2: Its great".
_NOTE_LINE = re.compile(r"^([^:]{1,40}):\s*(.+)$")
# A note label naming one epiphany level by number, such as "Flow 2".
_NUMBERED_LABEL = re.compile(r"^(.*?)\s*(\d)$")
# The part of an epiphany's game name that tells it apart, such as "Unbound" in "Flicker Blade (Unbound)".
_GAME_NAME_PART = re.compile(r"\((.+)\)$")

# Two picture hashes this close (out of 256 bits) are the same picture, re-encoded or resized by the sheet.
PICTURE_LABEL_DISTANCE = 12

# A local page listing every picture that still needs a label, written next to the download cache.
REVIEW_PAGE = "unidentified.html"

# Card match results by picture and candidate set, so a re-run skips the slow alignment search.
MATCH_CACHE = "card_matches.json"
# The OCR text of deck card pictures, so a re-run skips reading them again.
CARD_TEXT_CACHE = "card_text.json"

# The deck builder's card art, which the guide page shows. Matching against it finds cards of any character or the shared pool.
_NEUTRAL_ART_DIR = neutral_cards.DATA_DIR / neutral_cards.IMAGE_DIR
CARD_ART_DIRS = (card_art.COMBATANTS_DIR, _NEUTRAL_ART_DIR / "neutral", _NEUTRAL_ART_DIR / neutral_cards.MONSTER_SHARD)
# The faces the app can show, and the client's portrait folder a face is compared against.
APP_FACE_DIR = Path("api/assets/game/faces")
CLIENT_FACE_DIR = Path("face/character")
_APP_FACE = re.compile(r"^bookmark_face_character_map_(\d+)$")
_CLIENT_FACE = re.compile(r"^(?:shortcut_face_character|face_character|face_character_popup|portrait_character_crop)_(\d+)$")


class _Download:
    """One sheet picture, downloaded and decoded once per run however many tabs use it."""

    def __init__(self, data: bytes):
        """
        Args:
            data: The downloaded bytes.
        """
        self.data = data
        self.picture = images.load(data)
        self.kind = images.kind(self.picture)

    @cached_property
    def hash(self) -> int:
        """The picture's difference hash, worked out only when something needs it."""
        return images.dhash(self.picture)

    @cached_property
    def sha1(self) -> str:
        """The sha1 of the downloaded file, which tells identical files apart from near copies."""
        return hashlib.sha1(self.data).hexdigest()


class _Downloads:
    """The sheet's pictures by URL, each fetched and decoded once."""

    def __init__(self, fetcher: Fetcher):
        """
        Args:
            fetcher: Downloads the sheet's pictures.
        """
        self.fetcher = fetcher
        self._seen: dict[str, _Download] = {}

    def get(self, url: str) -> _Download:
        """
        One picture.

        Args:
            url: The picture's address.

        Returns:
            The decoded picture, shared by every use of the URL.
        """
        if url not in self._seen:
            self._seen[url] = _Download(self.fetcher.bytes(url))
        return self._seen[url]


@dataclass
class _Picture:
    """One distinct picture no matcher or label identified, and everywhere the sheet uses it."""

    # "face", "card" or "other", from the picture's shape.
    kind: str
    # The downloaded image, shown on the review page.
    data: bytes
    # Where it appears, such as "Tenebria!B11".
    refs: list[str] = field(default_factory=list)


class _PictureLabels:
    """
    Labels for sheet pictures, from the `_pictures` directive of the guides overrides.

    The sheet reuses the same picture on many tabs, so one label keyed by the picture's hash identifies every use of it.
    A label is `{"charResId": 1003}`, `{"cardId": "c_1003_uni1"}` or `{"skip": true}`.
    """

    def __init__(self, labels: dict[str, dict]):
        """
        Args:
            labels: Picture hash (hex, as shown on the review page) -> label.
        """
        self._labels = [(int(key, 16), value) for key, value in labels.items()]
        self.unidentified: dict[int, _Picture] = {}

    @property
    def empty(self) -> bool:
        """True when no picture has a label, so looking one up can be skipped."""
        return not self._labels

    def find(self, hash_value: int) -> dict:
        """
        The label for a picture.

        Args:
            hash_value: The picture's `images.dhash`.

        Returns:
            The label, or an empty dict when it has none.
        """
        for key, label in self._labels:
            if (key ^ hash_value).bit_count() <= PICTURE_LABEL_DISTANCE:
                return label
        return {}

    def unidentify(self, hash_value: int, data: bytes, kind: str, ref: str) -> None:
        """
        Record a picture nothing identified, merging re-encoded copies of the same picture.

        Args:
            hash_value: The picture's `images.dhash`.
            data: Its downloaded bytes.
            kind: "face", "card" or "other".
            ref: Where it appears.
        """
        key = next((known for known in self.unidentified if (known ^ hash_value).bit_count() <= PICTURE_LABEL_DISTANCE), hash_value)
        self.unidentified.setdefault(key, _Picture(kind, data)).refs.append(ref)


class _DeckPictures:
    """
    Deck cards waiting for their epiphany, and the rated pictures that show each epiphany.

    The sheet reuses one picture file for one epiphany, so a deck card with the same file as a rated picture of the same card
    is that rated level. Only identical files count, as two levels of one card share their art and hash almost alike. Every
    tab's rated rows are collected before any deck card is resolved.
    """

    def __init__(self):
        # (card id, picture sha1) -> the level of that rated picture.
        self.copies: dict[tuple[str, str], int] = {}
        # (deck card, its picture, its cell) still to be resolved.
        self.pending: list[tuple[dict, _Download, str]] = []
        # (card id, picture sha1) -> the OCR match of that picture, so copies of one picture in a deck are read once.
        self.matches: dict[tuple[str, str], card_text.Match | None] = {}

    def add_copy(self, card_id: str, download: _Download, level: int) -> None:
        """
        Remember a rated picture of one epiphany.

        Args:
            card_id: The card it shows.
            download: The picture.
            level: The epiphany level, from its position in the rated run.
        """
        self.copies.setdefault((card_id, download.sha1), level)

    def level_of(self, card_id: str, download: _Download) -> int | None:
        """
        The level a rated picture of the same card shows, when this picture is the same file.

        Args:
            card_id: The deck card.
            download: Its picture.

        Returns:
            The rated level, or None when no rated picture of the card is this file.
        """
        return self.copies.get((card_id, download.sha1))


def build(ctx: Context) -> TargetResult:
    """
    Import every character tab of the sheet.

    Args:
        ctx: The run context.

    Returns:
        One JSON file per guide, the module that lists them, a summary, and what could not be identified as issues.
    """
    overrides = ctx.overrides(NAME)
    cache = ctx.client.root / ".cache" / "guides"
    fetcher = Fetcher(cache)
    downloads = _Downloads(fetcher)
    faces = images.FaceMatcher(ctx.client.root / CLIENT_FACE_DIR)
    labels = _PictureLabels(overrides.directives.get("_pictures", {}))
    match_cache_path = cache / MATCH_CACHE
    match_cache: dict[str, str] = json.loads(match_cache_path.read_text(encoding="utf-8")) if match_cache_path.is_file() else {}
    tab_ids = overrides.directives.get("_tabs", {})
    names = {_normalise(entry["name"]): res_id for res_id, entry in roster.combatants().items()}
    own_cards = _cards_by_owner(ctx)
    sift_faces = _CachedSift("sift-faces", _face_art(ctx), match_cache)
    sift_cards = _CachedSift("sift-cards", _card_art(), match_cache, query_size=images.CARD_RENDER_SIZE, query_box=images.CARD_ART_WINDOW)
    card_names = _card_names(ctx)
    variants_of = lru_cache(maxsize=None)(partial(epiphany.variants, ctx))
    decks = _DeckPictures()
    issues: list[Issue] = []
    files: dict[Path, bytes] = {}
    guides: list[tuple[str, str, dict]] = []
    skipped: list[str] = []

    for tab_name, gid in tabs(fetcher.text(HTMLVIEW_URL)):
        res_id = tab_ids[tab_name] if tab_name in tab_ids else names.get(_normalise(tab_name.split("/")[0]))
        if res_id is None:
            skipped.append(tab_name)
            continue
        name = roster.combatants()[res_id]["name"]
        grid = parse_grid(fetcher.text(TAB_URL.format(gid=gid)))
        illustrations, card_ids = _card_candidates(ctx, own_cards.get(str(res_id), []))
        cards = _CachedCards(illustrations, card_ids, match_cache)
        builder = _GuideBuilder(ctx, downloads, faces, sift_faces, cards, sift_cards, card_names, variants_of, decks, overrides, labels, tab_name)
        guide = {
            "charResId": res_id,
            "name": name,
            "source": {"url": EDIT_URL.format(gid=gid), "label": {"en": SOURCE_LABEL}},
        }
        sections, updated = builder.sections(grid)
        if updated:
            guide["updated"] = updated
        guide["sections"] = sections
        guides.append((slug(name, _SLUG_MAX_LENGTH), name, guide))

    # Deck cards are resolved only now, so an exact copy can come from any tab's rated rows.
    text_cache_path = cache / CARD_TEXT_CACHE
    text_cache: dict[str, str] = json.loads(text_cache_path.read_text(encoding="utf-8")) if text_cache_path.is_file() else {}
    unknown_epiphanies: dict[str, _Picture] = {}
    for card, download, ref in decks.pending:
        if not _resolve_deck_card(card, download, ref, decks, overrides.entries, lambda data: card_text.read_card_text(data, text_cache), variants_of):
            _add_unknown_epiphany(unknown_epiphanies, download, ref)
    for guide_slug, _, guide in guides:
        files[DATA_DIR / f"{guide_slug}.guide.json"] = json_bytes(guide)

    issues.extend(overrides.validate({}, keyed_by_output=False))
    if skipped:
        issues.append(Issue("warning", f"{NAME}: tabs that are not a known character, skipped: {', '.join(skipped)}"))
    if labels.unidentified:
        uses = sum(len(picture.refs) for picture in labels.unidentified.values())
        issues.append(Issue("warning", (
            f"{NAME}: {len(labels.unidentified)} distinct picture(s) used {uses} times were not identified and are left out. "
            f"Label them in the `_pictures` directive of {OVERRIDES_FILE}, using the review page {cache / REVIEW_PAGE}"
        )))
    if unknown_epiphanies:
        uses = sum(len(picture.refs) for picture in unknown_epiphanies.values())
        issues.append(Issue("warning", (
            f"{NAME}: {uses} deck card(s) show an epiphany that could not be read and get no badge. Set it with a cell override such as "
            f'{{"epiphany": 2, "divine": "div_0098"}} in {OVERRIDES_FILE}, using the review page {cache / REVIEW_PAGE}'
        )))
    # These are caches for the next run and for review, not outputs, so they are written here rather than compared.
    cache.mkdir(parents=True, exist_ok=True)
    (cache / REVIEW_PAGE).write_bytes(_review_page(labels.unidentified, unknown_epiphanies))
    match_cache_path.write_bytes(json_bytes(dict(sorted(match_cache.items()))))
    text_cache_path.write_bytes(json_bytes(dict(sorted(text_cache.items()))))
    files[CONTENT_PATH] = _content_module(sorted(((guide_slug, name) for guide_slug, name, _ in guides), key=lambda guide: guide[1].casefold()))
    return TargetResult(files, f"{len(guides)} guides", issues)


def _cards_by_owner(ctx: Context) -> dict[str, list[str]]:
    """
    Every character card, grouped by the character it belongs to.

    Args:
        ctx: The run context.

    Returns:
        res_id (as written in the card id) -> its card ids, sorted.
    """
    owned: dict[str, list[str]] = {}
    for card_id in sorted(ctx.client.cards):
        match = _OWN_CARD.match(card_id)
        if match:
            owned.setdefault(match.group(1), []).append(card_id)
    return owned


def _card_candidates(ctx: Context, own_cards: list[str]) -> tuple[dict[str, Path], dict[str, str]]:
    """
    The illustrations one character's cards use.

    Args:
        ctx: The run context.
        own_cards: The guide character's card ids, sorted.

    Returns:
        Illustration name -> its PNG, and illustration name -> the first base card that uses it.
    """
    illustrations: dict[str, Path] = {}
    card_ids: dict[str, str] = {}
    for card_id in own_cards:
        if "_rsp" in card_id or card_id.endswith("_pot"):
            continue
        path = ctx.client.illustration(ctx.client.cards[card_id])
        if path is not None:
            illustrations.setdefault(path.stem, path)
            card_ids.setdefault(path.stem, card_id)
    return illustrations, card_ids


def _card_art() -> dict[str, list[Path]]:
    """
    The deck builder's card art, one entry per distinct image.

    Returns:
        Card id -> its WebP. Cards that share one image file are listed once, under the id with the fewest parts, such as
        `c_1012_srt4` rather than `c_1012_srt4_rsp1`, since the art alone cannot tell them apart.
    """
    by_content: dict[str, list[Path]] = {}
    for folder in CARD_ART_DIRS:
        for path in sorted((REPO_ROOT / folder).rglob("*.webp")):
            by_content.setdefault(hashlib.sha1(path.read_bytes()).hexdigest(), []).append(path)
    plainest = (min(paths, key=lambda path: (path.stem.count("_"), path.stem)) for paths in by_content.values())
    return {path.stem: [path] for path in plainest}


def _face_art(ctx: Context) -> dict[str, list[Path]]:
    """
    The client portraits of every character the app has a face for.

    Args:
        ctx: The run context.

    Returns:
        res_id (as text) -> its portraits in the client's `face/character` folder.
    """
    shown = {match.group(1) for path in (REPO_ROOT / APP_FACE_DIR).glob("*.png") if (match := _APP_FACE.match(path.stem))}
    faces: dict[str, list[Path]] = {}
    for path in sorted((ctx.client.root / CLIENT_FACE_DIR).glob("*.png")):
        match = _CLIENT_FACE.match(path.stem)
        if match and match.group(1) in shown:
            faces.setdefault(match.group(1), []).append(path)
    return faces


def _card_names(ctx: Context) -> dict[str, str]:
    """
    The display name of every card a guide can list.

    Args:
        ctx: The run context.

    Returns:
        Card id -> name, for character cards and for the deck builder's shared pool, whose ids differ from the client's.
    """
    names = {card_id: ctx.text(name, sentences=False) for card_id in ctx.client.cards if (name := ctx.resolver.card_name(card_id))}
    names.update({card["id"]: card["name"] for card in json.loads((REPO_ROOT / neutral_cards.OUTPUT_PATH).read_text(encoding="utf-8"))})
    return names


def _remembered(cache: dict[str, str], key: str, find) -> str:
    """
    A match result from the cache, found and stored on a miss.

    Args:
        cache: Cache key -> match, or "" for no match. Updated in place.
        key: This picture's cache key.
        find: Returns the match, or None, when the key is not cached yet.

    Returns:
        The cached match, or "" for no match.
    """
    if key not in cache:
        cache[key] = find() or ""
    return cache[key]


class _CachedSift:
    """A SIFT matcher over one pool, built only on the first cache miss, with results remembered across runs."""

    def __init__(self, pool: str, candidates: dict[str, list[Path]], cache: dict[str, str], **options):
        """
        Args:
            pool: The pool's name in cache keys, such as "sift-cards".
            candidates: Key -> its images.
            cache: "<picture sha1>:<pool>:<candidates and settings sha1>" -> key, or "" for no match. Updated in place.
            options: Passed on to `images.SiftMatcher`.
        """
        self.pool = pool
        self.candidates = candidates
        self.cache = cache
        self.options = options
        # The matcher's settings are part of the signature, so tuning a threshold re-matches every picture.
        settings = sorted((name, value) for name, value in vars(images).items() if name.startswith("SIFT_"))
        self.signature = hashlib.sha1(f"{sorted(candidates)}{settings}{sorted(options.items())}".encode("utf-8")).hexdigest()[:12]
        self._matcher: images.SiftMatcher | None = None

    def match(self, picture: Image.Image, data: bytes) -> str | None:
        """
        The candidate a picture shows.

        Args:
            picture: The decoded picture.
            data: Its downloaded bytes, which key the cache.

        Returns:
            The candidate's key, or None when there is no clear match.
        """
        def find():
            if self._matcher is None:
                self._matcher = images.SiftMatcher(self.candidates, **self.options)
            return self._matcher.match(picture)

        return _remembered(self.cache, f"{hashlib.sha1(data).hexdigest()}:{self.pool}:{self.signature}", find) or None


class _CachedCards:
    """One character's card matcher, with results remembered across runs."""

    def __init__(self, illustrations: dict[str, Path], card_ids: dict[str, str], cache: dict[str, str]):
        """
        Args:
            illustrations: Illustration name -> its PNG. The matcher is only built from these on the first cache miss.
            card_ids: Illustration name -> the base card id it belongs to.
            cache: "<picture sha1>:<candidates sha1>" -> illustration name, or "" for no match. Updated in place.
        """
        self.illustrations = illustrations
        self._matcher: images.CardMatcher | None = None
        self.card_ids = card_ids
        self.cache = cache
        self.signature = hashlib.sha1(",".join(sorted(card_ids)).encode("utf-8")).hexdigest()[:12]

    def card_id(self, picture, data: bytes) -> str | None:
        """
        The base card a render shows, among this character's own cards.

        Args:
            picture: The decoded render.
            data: Its downloaded bytes, which key the cache.

        Returns:
            The card id, or None when there is no clear match.
        """
        def find():
            if self._matcher is None:
                self._matcher = images.CardMatcher(self.illustrations)
            return self._matcher.match(picture)

        return self.card_ids.get(_remembered(self.cache, f"{hashlib.sha1(data).hexdigest()}:{self.signature}", find))


class _GuideBuilder:
    """Turns one tab's cell grid into guide sections."""

    def __init__(self, ctx: Context, downloads: _Downloads, faces: images.FaceMatcher, sift_faces: _CachedSift, cards: _CachedCards,
                 sift_cards: _CachedSift, card_names: dict[str, str], variants_of, decks: _DeckPictures, overrides: Overrides,
                 labels: _PictureLabels, tab_name: str):
        """
        Args:
            ctx: The run context.
            downloads: The sheet's pictures, decoded once per run.
            faces: Identifies face portraits by hash.
            sift_faces: Identifies the face portraits the hash misses.
            cards: Identifies this character's card renders.
            sift_cards: Identifies the card renders `cards` misses, among every card in the deck builder.
            card_names: Card id -> display name, written next to each listed card.
            variants_of: Card id -> its `epiphany.variants`, shared by every tab.
            decks: Collects rated pictures and the deck cards to resolve once every tab is read.
            overrides: The guides overrides, whose entries can label one cell as "<tab>!<cell>".
            labels: Labels by picture, which also collect what nothing identified.
            tab_name: The sheet tab, used in cell override keys and references.
        """
        self.ctx = ctx
        self.downloads = downloads
        self.faces = faces
        self.sift_faces = sift_faces
        self.cards = cards
        self.sift_cards = sift_cards
        self.card_names = card_names
        self.variants_of = variants_of
        self.decks = decks
        self.overrides = overrides
        self.labels = labels
        self.tab_name = tab_name

    def sections(self, grid: dict[tuple[int, int], Cell]) -> tuple[list[dict], str | None]:
        """
        Every section of the guide, one per band of rows.

        Args:
            grid: The tab's cells.

        Returns:
            The sections, in sheet order, without empty ones, and the sheet's edit date if it has one.
        """
        sections: list[dict] = []
        for band in _bands(grid):
            blocks: list[dict] = []
            title = None
            for panel in _panels(band):
                panel_title, panel_blocks, title_shown = self._panel(panel)
                if title is None:
                    title = panel_title
                elif panel_title and not title_shown:
                    # A later panel's heading would otherwise be lost, so it leads that panel's blocks instead.
                    panel_blocks.insert(0, self._prose(panel_title))
                blocks.extend(panel_blocks)
            blocks = [self._deck_or_list(block) if block["type"] == "card-list" else block for block in _attach_notes(blocks)]
            if not blocks:
                continue
            sections.append({"title": self.ctx.text(title, soften=True, sentences=False) if title else None, "blocks": blocks})
        return _tidy_sections(sections)

    def _panel(self, cells: list[Cell]) -> tuple[str | None, list[dict], bool]:
        """
        One panel's blocks.

        Args:
            cells: The panel's cells within one band.

        Returns:
            The panel's heading if it has one, its blocks in reading order, and whether the heading already appears in
            those blocks (as the names of the pictures under it), so it need not be repeated.
        """
        rows = _rows(cells)
        blocks: list[dict] = []
        title = None
        # A label row right above pictures may name them, so it is held until the pictures show whether it was used.
        held: str | None = None
        title_shown = False
        index = 0
        while index < len(rows):
            row = rows[index]
            if any(cell.images for cell in row):
                consumed, new_blocks, named = self._picture_rows(rows, index)
                if held and not named:
                    # Pictures that do not take names (set icons, banners) leave the heading as an ordinary heading.
                    if title is None and all(block["type"] in ("card-list", "team-grid") for block in blocks):
                        title = held
                    else:
                        blocks.append(self._prose(held))
                elif held and title is None:
                    title, title_shown = held, True
                held = None
                blocks.extend(new_blocks)
                index += consumed
                continue
            texts = [cell.text for cell in row if cell.text]
            if len(texts) == 2 and texts[0].casefold().endswith("code"):
                blocks.append({"type": "rating-list", "items": [{"label": texts[0], "text": {"en": texts[1]}}]})
            elif _is_label_row(texts):
                line = " | ".join(texts)
                if index + 1 < len(rows) and any(cell.images for cell in rows[index + 1]):
                    held = line
                # Otherwise the first label row is the heading, even when a row of pictures sits above it.
                elif title is None and all(block["type"] in ("card-list", "team-grid") for block in blocks):
                    title = line
                else:
                    blocks.append(self._prose(line))
            else:
                blocks.extend(self._prose(text) for text in texts)
            index += 1
        return title, blocks, title_shown

    def _picture_rows(self, rows: list[list[Cell]], start: int) -> tuple[int, list[dict], bool]:
        """
        A run of picture rows and the ratings under them.

        Args:
            rows: The panel's rows.
            start: The first picture row.

        Returns:
            How many rows were consumed, the blocks they became, and whether the label row above them was used to name
            them (as partner names or team group titles).
        """
        end = start
        while end < len(rows) and any(cell.images for cell in rows[end]):
            end += 1
        ratings: dict[int, str] = {}
        if end < len(rows) and all(_RATING.match(cell.text) for cell in rows[end] if cell.text) and any(cell.text for cell in rows[end]):
            ratings = {cell.col: cell.text for cell in rows[end] if cell.text}
            consumed = end - start + 1
        else:
            consumed = end - start
        names = {cell.col: cell.text for cell in rows[start - 1] if cell.text} if start > 0 and _is_label_row([c.text for c in rows[start - 1] if c.text]) else {}

        cards: list[dict] = []
        face_rows: list[list[tuple[int, int]]] = []
        for row in rows[start:end]:
            last_card, epiphany = None, 0
            face_row: list[tuple[int, int]] = []
            for cell in row:
                ref = f"{self.tab_name}!{cell.ref}"
                for url in cell.images:
                    download = self.downloads.get(url)
                    kind = download.kind
                    found = {} if self.labels.empty else self.labels.find(download.hash)
                    label = {**found, **self.overrides.entries.get(ref, {})}
                    if label.get("skip"):
                        continue
                    if "charResId" in label or (kind == "face" and "cardId" not in label):
                        res_id = label.get("charResId") or self._face(download)
                        if res_id is None:
                            self.labels.unidentify(download.hash, download.data, kind, ref)
                        else:
                            face_row.append((cell.col, res_id))
                    elif "cardId" in label or kind == "card":
                        card_id = label.get("cardId") or self.cards.card_id(download.picture, download.data) or self.sift_cards.match(download.picture, download.data)
                        if card_id is None:
                            self.labels.unidentify(download.hash, download.data, kind, ref)
                            last_card = None
                            continue
                        epiphany = epiphany + 1 if card_id == last_card else 1
                        last_card = card_id
                        cards.append({"cardId": card_id, "col": cell.col, "epiphany": epiphany, "picture": (download, ref)})
                    else:
                        # Set icons, banners and the like. Listed for review so they can be labelled or skipped.
                        self.labels.unidentify(download.hash, download.data, kind, ref)
            if face_row:
                face_rows.append(face_row)

        blocks = []
        named = False
        if cards:
            blocks.append(self._card_list(cards, ratings))
        if face_rows:
            face_block, named = self._face_block(face_rows, ratings, names)
            blocks.append(face_block)
        return consumed, blocks, named

    def _face(self, download: _Download) -> int | None:
        """
        The character a face portrait shows.

        Args:
            download: The sheet's picture.

        Returns:
            The res_id, from the portrait hash or else from SIFT, or None when neither finds a clear match.
        """
        res_id = self.faces.match(download.picture, hash_value=download.hash)
        if res_id is None and (found := self.sift_faces.match(download.picture, download.data)):
            res_id = int(found)
        return res_id

    def _card_list(self, cards: list[dict], ratings: dict[int, str]) -> dict:
        """
        Cards with their names, costs and the rating under each one.

        Args:
            cards: Identified cards with their column and epiphany position.
            ratings: column -> rating text.

        Returns:
            A card-list block. Consecutive rated renders of the same card are its epiphany levels, folded into one item.
        """
        # Only rated rows list a card's epiphany variants. Elsewhere a repeated card is just another copy in a deck.
        variants = _complete_runs(cards, self.variants_of) if ratings else set()
        items = []
        for card in cards:
            card_id = card["cardId"]
            item = {"cardId": card_id}
            if card_id in self.card_names:
                item["name"] = self.card_names[card_id]
            if card_id in self.ctx.client.cards:
                item["cost"] = epiphany.printed_cost(self.ctx, card_id)
            item["note"] = {"en": ""}
            if card["col"] in ratings:
                item["rating"] = ratings[card["col"]]
            if card_id in variants:
                item["level"] = card["epiphany"]
                self.decks.add_copy(card_id, card["picture"][0], card["epiphany"])
            # Kept until the block is known to be a deck or not, then dropped by `_deck_or_list`.
            item["_picture"] = card["picture"]
            items.append(item)
        return {"type": "card-list", "items": _fold(items, self.variants_of)}

    def _deck_or_list(self, block: dict) -> dict:
        """
        A card-list as a deck when it is a plain list of cards, its cards queued to have their epiphany resolved.

        Args:
            block: A card-list block whose items still hold their pictures.

        Returns:
            The deck block, or the card-list without the pictures.
        """
        pictures = [item.pop("_picture", None) for item in block["items"]]
        deck = _as_deck(block)
        if deck is None:
            return block
        for card, picture in zip(deck["cards"], pictures):
            if picture:
                self.decks.pending.append((card, *picture))
        return deck

    def _face_block(self, face_rows: list[list[tuple[int, int]]], ratings: dict[int, str], names: dict[int, str]) -> tuple[dict, bool]:
        """
        Faces as partner picks (when rated) or as team rosters.

        Args:
            face_rows: Per picture row, (column, res_id) pairs.
            ratings: column -> rating text, from the row under the faces.
            names: column -> label text, from the row above the faces.

        Returns:
            The block, and whether `names` was used. Rated faces become a partner-list. Unrated faces under a heading for
            every column become a team-grid with one group per column (such as "Draw Engines"), otherwise one per row.
        """
        if ratings and len(face_rows) == 1:
            items = []
            for col, res_id in face_rows[0]:
                name = names.get(col) or self._name(res_id)
                items.append({"charResId": res_id, "name": name, "rating": ratings.get(col, ""), "note": {"en": ""}})
            return {"type": "partner-list", "items": items}, bool(names)
        columns = sorted({col for row in face_rows for col, _ in row})
        if names and all(col in names for col in columns):
            groups = [{"title": {"en": self.ctx.text(names[col], soften=True, sentences=False)}, "members": self._members(res_id for row in face_rows for c, res_id in row if c == col)}
                      for col in columns]
            return {"type": "team-grid", "groups": groups}, True
        return {"type": "team-grid", "groups": [{"members": self._members(res_id for _, res_id in row)} for row in face_rows]}, False

    def _members(self, res_ids) -> list[dict]:
        return [{"charResId": res_id, "name": self._name(res_id)} for res_id in res_ids]

    def _name(self, res_id: int) -> str:
        character = roster.combatants().get(res_id)
        if character:
            return character["name"]
        text = self.ctx.client.text(f"char_base@name@{res_id}") or self.ctx.client.text(f"partner_base@name@{res_id}")
        return text or str(res_id)

    def _prose(self, text: str) -> dict:
        return {"type": "prose", "body": {"en": self.ctx.text(text, soften=True, sentences=False)}}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Grid helpers


def _tidy_sections(sections: list[dict]) -> tuple[list[dict], str | None]:
    """
    Sections as the page shows them.

    Args:
        sections: Each band's title (None when it has none) and blocks.

    Returns:
        The sections with ids, and the sheet's edit date. The "Last Edit" section is dropped for that date. An untitled section is
        named for what it holds, and one-line lists of sets (as a title or a prose line) become set cards.
    """
    tidied: list[dict] = []
    used_ids: set[str] = set()
    updated = None
    for section in sections:
        blocks = section["blocks"]
        texts = [block["body"]["en"].strip() if block["type"] == "prose" else "" for block in blocks]
        if all(_LAST_EDIT.match(text) for text in texts):
            updated = next((text for text in texts if any(char.isdigit() for char in text)), updated)
            continue
        title = section["title"] or _untitled_name(blocks)
        blocks = [_set_block(block) for block in blocks]
        if title_sets := set_line(title):
            blocks.insert(0, {"type": "set-list", "items": title_sets})
        tidied.append({"id": _unique(slug(title, _SLUG_MAX_LENGTH) or "part", used_ids), "title": {"en": title}, "blocks": blocks})
    return tidied, updated


def _untitled_name(blocks: list[dict]) -> str:
    """A name for a section the sheet gives no heading, from what it holds."""
    types = {block["type"] for block in blocks}
    if any(block["type"] == "card-list" and any("rating" in item for item in block["items"]) for block in blocks):
        return "Card ratings"
    if "partner-list" in types:
        return "Partners"
    if "team-grid" in types:
        return "Teams"
    return "Notes"


def _set_block(block: dict) -> dict:
    """A prose line listing sets as a set-list block, any other block as it is."""
    items = set_line(block["body"]["en"]) if block["type"] == "prose" else None
    return {"type": "set-list", "items": items} if items else block


def _complete_runs(cards: list[dict], variants_of) -> set[str]:
    """
    The cards whose rated renders are one whole run of their epiphany levels, so each render's position is its level.

    Args:
        cards: Identified cards with their epiphany position in the row.
        variants_of: Card id -> its `epiphany.variants`.

    Returns:
        The card ids whose positions are exactly 1 to their last level. A run that was cut short, restarted or split gives
        no levels, as a wrong level is worse than none.
    """
    positions: dict[str, list[int]] = {}
    for card in cards:
        positions.setdefault(card["cardId"], []).append(card["epiphany"])
    return {card_id for card_id, found in positions.items() if found == list(range(1, len(variants_of(card_id))))}


def _fold(items: list[dict], variants_of) -> list[dict]:
    """
    Each rated run of one card's renders as one item that lists its epiphanies.

    Args:
        items: Card-list items. Those in a rated run carry their epiphany `level`, by position.
        variants_of: Card id -> its `epiphany.variants`.

    Returns:
        The items, each run folded into one item whose `epiphanies` hold every level's name, cost, rating and note. A card with
        no variants is kept as it is, without its level.
    """
    folded: list[dict] = []
    for item in items:
        item = dict(item)
        level = item.pop("level", None)
        variant = next((variant for variant in variants_of(item["cardId"]) if variant.level == level), None) if level else None
        if variant is None:
            folded.append(item)
            continue
        entry = {"level": level, "name": variant.name, "cost": variant.cost}
        if "rating" in item:
            entry["rating"] = item["rating"]
        entry["note"] = {"en": ""}
        last = folded[-1] if folded else None
        if last and last["cardId"] == item["cardId"] and last.get("epiphanies") and last["epiphanies"][-1]["level"] < level:
            last["epiphanies"].append(entry)
        else:
            head = {key: item[key] for key in ("cardId", "name") if key in item}
            folded.append({**head, "note": {"en": ""}, "epiphanies": [entry]})
    return folded


def _attach_notes(blocks: list[dict]) -> list[dict]:
    """
    "Name: note" prose lines moved onto the card or partner they name.

    Args:
        blocks: A section's blocks.

    Returns:
        The blocks. Prose straight after a card-list or partner-list gives up each line that names one of its items, and the
        rest stays in order. A prose block left empty is dropped.
    """
    kept: list[dict] = []
    for block in blocks:
        previous = kept[-1] if kept else None
        if block["type"] != "prose" or not previous or previous["type"] not in ("card-list", "partner-list"):
            kept.append(block)
            continue
        rest = []
        for line in block["body"]["en"].split("\n"):
            match = _NOTE_LINE.match(line)
            target = _note_target(previous["items"], match.group(1)) if match else None
            if target is None:
                rest.append(line)
                continue
            note = target["note"]["en"]
            target["note"] = {"en": f"{note}\n{match.group(2)}" if note else match.group(2)}
        if any(line.strip() for line in rest):
            kept.append({**block, "body": {"en": "\n".join(rest)}})
    return kept


def _as_deck(block: dict) -> dict | None:
    """
    A card-list as a deck strip, when it is a plain list of cards.

    Args:
        block: A card-list block.

    Returns:
        A deck block with every copy, or None when any card has a rating, a note or epiphanies.
    """
    if any(item.get("rating") or item["note"]["en"] or "epiphanies" in item for item in block["items"]):
        return None
    return {"type": "deck", "cards": [{key: item[key] for key in ("cardId", "name", "cost") if key in item} for item in block["items"]]}


def _resolve_deck_card(card: dict, download: _Download, ref: str, decks: _DeckPictures, overrides: dict[str, dict], read, variants_of) -> bool:
    """
    Set the epiphany a deck card shows, its added divine or common line, and the cost that gives it.

    Args:
        card: The deck card, updated in place.
        download: Its picture.
        ref: Its cell, such as "Rossweisse!C10".
        decks: The rated pictures, for an exact copy.
        overrides: Guides override entries by cell. One can give `epiphany` (0 for the base card) and `divine` or `common`.
        read: Picture bytes -> its OCR text.
        variants_of: Card id -> its `epiphany.variants`.

    Returns:
        True when the epiphany is known, or the card has none to find. False when nothing read it clearly.
    """
    variants = {variant.level: variant for variant in variants_of(card["cardId"])}
    if not variants:
        return True
    entry = overrides.get(ref, {})
    extra = None
    if "epiphany" in entry:
        level = entry["epiphany"]
        extra = _extra(entry.get("divine") or entry.get("common"))
    elif (level := decks.level_of(card["cardId"], download)) is None:
        key = (card["cardId"], download.sha1)
        if key not in decks.matches:
            # The emblem only picks which lines to try. Text alone mixes up divine lines that read alike.
            god = card_text.match_god(download.picture)
            extras = [line for line in epiphany.divine_epiphanies() if line.god == god] if god else epiphany.common_epiphanies()
            decks.matches[key] = card_text.match_epiphany(read(download.data), list(variants.values()), extras)
        match = decks.matches[key]
        if match is None:
            return False
        level, extra = match.level, match.extra
    variant = variants.get(level)
    if variant is None:
        return False
    card["cost"] = epiphany.card_cost(variant.cost, extra)
    card["epiphany"] = {"level": level, "name": variant.name, "text": {"en": variant.text}}
    if extra:
        card["extra"] = {"id": extra.id, **({"god": extra.god} if extra.god else {}), "text": {"en": extra.text}}
    return True


def _add_unknown_epiphany(unknown: dict[str, _Picture], download: _Download, ref: str) -> None:
    """
    Record a deck card whose epiphany could not be read, for the review page.

    Args:
        unknown: Picture sha1 -> the picture and its cells. Updated in place.
        download: The card's picture.
        ref: Its cell.
    """
    # Keyed by the exact file, as two levels of one card hash almost alike and one entry must not stand for both.
    unknown.setdefault(download.sha1, _Picture("card", download.data)).refs.append(ref)


def _extra(extra_id: str | None) -> Extra | None:
    """The divine or common epiphany line with this id, or None when there is none."""
    return next((line for line in [*epiphany.divine_epiphanies(), *epiphany.common_epiphanies()] if line.id == extra_id), None)


def _note_target(items: list[dict], label: str) -> dict | None:
    """
    The item, or epiphany of one, that a note label names.

    Args:
        items: The listed cards or partners.
        label: The text before the colon, such as "Tassel", "Flow 2" or "Unbound".

    Returns:
        The epiphany named by its game name ("Unbound") or by a word of the card's name and its level ("Flow 2"), else the item
        whose name or a word of it is the label. None when nothing fits.
    """
    wanted = label.strip().lower()
    if not wanted:
        return None
    numbered = _NUMBERED_LABEL.match(wanted)
    for item in items:
        epiphanies = item.get("epiphanies", [])
        for entry in epiphanies:
            part = _GAME_NAME_PART.search(entry["name"])
            if part and part.group(1).lower() == wanted:
                return entry
        name = item.get("name", "").lower()
        words = re.split(r"[\s:]+", name)
        if numbered:
            base, level = numbered.group(1), int(numbered.group(2))
            if base in words or base == name:
                found = next((entry for entry in epiphanies if entry["level"] == level), None)
                if found:
                    return found
        elif name == wanted or wanted in words:
            return item
    return None


def _bands(grid: dict[tuple[int, int], Cell]) -> list[list[Cell]]:
    """
    The tab split into bands of consecutive non-empty rows.

    Args:
        grid: The tab's cells.

    Returns:
        Each band's cells, in sheet order. The first band is dropped when it is only the sheet's "Glossary Link" header.
    """
    bands: list[list[Cell]] = []
    previous = None
    for key in sorted(grid):
        row = key[0]
        if previous is None or row > previous + 1:
            bands.append([])
        bands[-1].append(grid[key])
        previous = row
    return [band for band in bands if not (len(band) == 1 and band[0].text.casefold().startswith("glossary link"))]


def _panels(band: list[Cell]) -> list[list[Cell]]:
    """
    A band split into its side-by-side panels.

    Args:
        band: The band's cells.

    Returns:
        Each panel's cells, left to right.
    """
    panels: dict[int, list[Cell]] = {}
    for cell in band:
        panels.setdefault(max(cell.col - 1, 0) // PANEL_WIDTH, []).append(cell)
    return [panels[index] for index in sorted(panels)]


def _rows(cells: list[Cell]) -> list[list[Cell]]:
    """The cells grouped by row, top to bottom, each row left to right."""
    rows: dict[int, list[Cell]] = {}
    for cell in cells:
        rows.setdefault(cell.row, []).append(cell)
    return [sorted(rows[row], key=lambda cell: cell.col) for row in sorted(rows)]


def _is_label_row(texts: list[str]) -> bool:
    """Whether a row's texts are all short, single-line labels."""
    return bool(texts) and all(len(text) <= _LABEL_MAX_LENGTH and "\n" not in text and not _RATING.match(text) for text in texts)


def _normalise(name: str) -> str:
    """A name reduced to lower-case letters and digits, for matching tab names to characters."""
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _unique(candidate: str, used: set[str]) -> str:
    """`candidate`, or `candidate-2`, `-3`... when it is taken. Records the result in `used`."""
    result, number = candidate, 2
    while result in used:
        result, number = f"{candidate}-{number}", number + 1
    used.add(result)
    return result


def _review_page(pictures: dict[int, _Picture], unknown_epiphanies: dict[str, _Picture] | None = None) -> bytes:
    """
    A local page listing every picture that still needs a label, most used first.

    Args:
        pictures: Picture hash -> the picture and where it is used.
        unknown_epiphanies: Picture sha1 -> a deck card picture whose epiphany could not be read, listed under their own heading.

    Returns:
        The HTML page. Each entry shows the picture, how to label it (the hash to use as its `_pictures` key, or a cell override
        for a deck card), and where it appears.
    """
    style = "body{font-family:sans-serif;background:#111;color:#ddd}figure{display:inline-block;width:260px;margin:8px;vertical-align:top}"
    style += "img{max-width:250px;max-height:200px}code{font-size:10px;word-break:break-all;color:#c084fc}"
    title = f"{len(pictures)} unidentified guide pictures"
    entries = _review_entries(pictures, lambda key: f'<code>"{key:064x}"</code>')
    page = f"<!doctype html><meta charset=utf-8><title>{title}</title><style>{style}</style><h1>{title}</h1>{entries}"
    if unknown_epiphanies:
        page += f"<h1>Deck cards with an unknown epiphany</h1>{_review_entries(unknown_epiphanies, lambda key: 'Set with a cell override')}"
    return f"{page}\n".encode("utf-8")


def _review_entries(pictures: dict, how_to_label) -> str:
    """The review page entries for some pictures, most used first, each captioned with `how_to_label(key)` as HTML."""
    entries = []
    for key, picture in sorted(pictures.items(), key=lambda item: (-len(item[1].refs), item[0])):
        mime = Image.MIME.get(Image.open(io.BytesIO(picture.data)).format or "", "image/png")
        source = f"data:{mime};base64,{base64.b64encode(picture.data).decode('ascii')}"
        refs = ", ".join(picture.refs[:8]) + (f" and {len(picture.refs) - 8} more" if len(picture.refs) > 8 else "")
        entries.append(
            f'<figure><img src="{source}" alt=""><figcaption>{how_to_label(key)}<br>{picture.kind}, used {len(picture.refs)} time(s): '
            f"{html.escape(refs)}</figcaption></figure>"
        )
    return "".join(entries)


def _content_module(guides: list[tuple[str, str]]) -> bytes:
    """
    The module that lists every guide.

    Args:
        guides: (slug, name) pairs in display order.

    Returns:
        TypeScript source for `guides-content.ts`.
    """
    imports = "\n".join(f"import {_identifier(slug)} from './data/{slug}.guide.json'" for slug, _ in guides)
    entries = ",\n".join(f"  {_identifier(slug)} as Guide" for slug, _ in guides)
    return (
        "// Generated by `python -m scripts.datagen guides` from the community Google Sheet. Do not edit by hand.\n"
        f"{imports}\n"
        "import type { Guide } from './guides.types'\n\n"
        f"export const GUIDES: Guide[] = [\n{entries},\n]\n\n"
        "export function getGuide(charResId: number): Guide | undefined {\n"
        "  return GUIDES.find(g => g.charResId === charResId)\n"
        "}\n"
    ).encode("utf-8")


def _identifier(slug: str) -> str:
    """A slug as a camelCase TypeScript identifier ending in "Json", such as "meiLinJson"."""
    parts = slug.split("-")
    return parts[0] + "".join(part.capitalize() for part in parts[1:]) + "Json"
