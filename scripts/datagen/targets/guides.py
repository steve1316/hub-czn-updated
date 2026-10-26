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
import difflib
import hashlib
import html
import io
import json
import re
from dataclasses import dataclass, field
from itertools import groupby
from functools import cached_property, lru_cache, partial
from pathlib import Path

from PIL import Image

from scripts.datagen import card_text, epiphany, guides_qc, images, potential_overlay, roster
from scripts.datagen.art import wanted, webp
from scripts.datagen.epiphany import Extra, Variant
from api.game_data.sets import SETS
from scripts.datagen.set_names import set_item, set_line
from scripts.datagen.naming import slug
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes
from scripts.datagen.targets import card_art, neutral_cards
from scripts.datagen.sheet import EDIT_URL, HTMLVIEW_URL, TAB_URL, Cell, Fetcher, layout, parse_grid, tabs

NAME = "guides"
OFFLINE = False

DATA_DIR = Path("src/pages/guides/data")
CONTENT_PATH = Path("src/pages/guides/guides-content.ts")
# Each guide's potentials tree picture, named after the guide. Only ever added, like card art.
POTENTIALS_DIR = DATA_DIR / "potentials"
POTENTIALS_QUALITY = 90
# The client table that tells which stat each character's two stat nodes give.
POTENTIAL_NODE_TABLE = "potential_node@potential_node.json"
# Wide pictures nothing identified (relic screenshot strips, skill clips) ship as image blocks, named after their hash. Only ever added.
IMAGES_DIR = DATA_DIR / "images"
IMAGE_QUALITY = 85
# An unmatched picture this small in both directions is an icon and is dropped without a review entry.
ICON_MAX_SIZE = 130
# An unmatched picture at least this many times wider than tall is a strip worth showing.
STRIP_MIN_RATIO = 2.2
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
# A numbered note line that uses a comma or a quote instead of the colon, such as "OUAT 1, 1 cost is bad" or 'Truth 3" Just damage'.
_NUMBERED_NOTE_LINE = re.compile(r"^(.*?\s*\d)\s*[,\"]\s*(.+)$")
# A line that starts with a short name and a level number then a separator, such as "Whirl 2: x", for the positional rule.
_SHORT_NUMBERED_LINE = guides_qc.NUMBERED_LINE
# A note label's base word must be at least this close to a word of the card's name, so a typo such as "Whiirl" still finds "Whirl".
_NOTE_NAME_CLOSENESS = 0.8
# A note label naming one epiphany level by number, such as "Flow 2".
_NUMBERED_LABEL = re.compile(r"^(.*?)\s*(\d)$")
# A word with its ending in brackets, such as "Cresc(endo)", which names the whole word.
_WORD_ENDING = re.compile(r"(?<=\w)\((\w+)\)")
# The part of an epiphany's game name that tells it apart, such as "Unbound" in "Flicker Blade (Unbound)".
_GAME_NAME_PART = re.compile(r"\((.+)\)$")
# The potentials colour legend, which starts "Purple: Main Damage Boosts", and one of its lines.
_LEGEND = re.compile(r"^\s*purple\s*:", re.IGNORECASE)
_LEGEND_LINE = re.compile(r"^\s*(purple|gold|blue)\s*:\s*(.+?)\s*$", re.IGNORECASE)
# An ego manifestation note's level line, "E1:" or a bare "E1", but not "E2's damage" inside a note.
_EGO_LEVEL = re.compile(r"^\s*E[1-6](?:\s*:|\s*$)", re.MULTILINE)
# An ego level is shown bold when more than this share of its characters are bold in the sheet.
_BOLD_SHARE = 0.9
# The potentials band's own headings, such as "Potential Priority:" and "Ego Menifestation:", which the page title replaces.
_POTENTIALS_HEADING = re.compile(r"potential|ego m[ae]nifestation", re.IGNORECASE)
POTENTIALS_TITLE = "Potentials & Ego"

# Every guide shows these pages, in this order, with the sheet's bands sorted into them. A page the sheet has nothing for is
# still shown, marked missing.
PAGES = [("playstyle", "Playstyle"), ("decks", "Decks"), ("partners", "Partners"), ("relics", "Relics"), ("potentials", POTENTIALS_TITLE),
         ("card-ratings", "Card Ratings"), ("teams", "Example Teams")]
# Seasonal cards, chaos notes, refinements and the like, which only some guides have. Shown last, and only when there are any.
EXTRAS_PAGE = ("seasons-chaos", "Seasons & Chaos")
_PAGE_IDS = [page_id for page_id, _ in [*PAGES, EXTRAS_PAGE]]
# Pages whose band titles only repeat the page name ("Card ratings", "Rossweisse Example Teams") or list its partners, so they are not shown.
_UNTITLED_PAGES = {"partners", "potentials", "card-ratings", "teams"}
# A band before the partners that is about how the character plays, though it is not the first band.
_PLAYSTYLE_TITLE = re.compile(r"notes|patch|season", re.IGNORECASE)

# Two picture hashes this close (out of 256 bits) are the same picture, re-encoded or resized by the sheet.
PICTURE_LABEL_DISTANCE = 12

# A local page listing every picture that still needs a label, written next to the download cache.
REVIEW_PAGE = "unidentified.html"

# The quality report of the last run, next to the download cache.
QC_REPORT = "qc.md"

# The OCR text of card title bars, so a re-run skips reading them again.
CARD_TITLE_CACHE = "card_titles.json"
# A read title must be this close to a card name, with at least this many letters.
_TITLE_CLOSENESS = 0.8
# A title this close to a card name overrules the art, which cards of one name and different ids (a tutorial copy) can share.
_TITLE_TRUSTED = 0.9
_TITLE_MIN_LETTERS = 4
# The suffix that makes a card id an epiphany of its base card, such as `c_1012_srt4_rsp1`.
_EPIPHANY_ID = re.compile(r"_rsp\d+$")

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
# The memory fragment piece art the app ships. The sheet shows these pieces under each relic loadout's set name.
PIECE_DIR = Path("api/assets/game/pieces")
_PIECE_FILE = re.compile(r"^item_piece_set_(\d+)_\d+$")


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

    def get(self, url: str, key: str) -> _Download:
        """
        One picture.

        Args:
            url: The picture's address.
            key: What names the picture in the cache across runs, from `_GuideBuilder._picture_key`.

        Returns:
            The decoded picture, shared by every use of the URL.
        """
        if url not in self._seen:
            self._seen[url] = _Download(self.fetcher.bytes(url, key))
        else:
            # Two cells share an address on some runs and not on others, so each keeps its own copy for the runs they do not.
            self.fetcher.store(key, self._seen[url].data)
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
    A label is `{"charResId": 1003}`, `{"cardId": "c_1003_uni1"}`, `{"setId": 11}` (a memory fragment piece) or `{"skip": true}`.
    A card label can also carry a `name` and a `persona` art key, for a Persona card whose engravings give it its own name and art.
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
            The nearest label within `PICTURE_LABEL_DISTANCE` bits, or an empty dict when it has none.
        """
        nearest = min(self._labels, key=lambda entry: (entry[0] ^ hash_value).bit_count(), default=None)
        if nearest is not None and (nearest[0] ^ hash_value).bit_count() <= PICTURE_LABEL_DISTANCE:
            return nearest[1]
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
        One JSON file per guide, the module that lists them, each potentials tree picture, a summary, and what could not be identified as issues.
    """
    overrides = ctx.overrides(NAME)
    cache = ctx.client.root / ".cache" / "guides"
    fetcher = Fetcher(cache / "pictures")
    downloads = _Downloads(fetcher)
    faces = images.FaceMatcher(ctx.client.root / CLIENT_FACE_DIR)
    labels = _PictureLabels(overrides.directives.get("_pictures", {}))
    match_cache_path = cache / MATCH_CACHE
    match_cache = _load_cache(match_cache_path)
    tab_ids = overrides.directives.get("_tabs", {})
    names = {_normalise(entry["name"]): res_id for res_id, entry in roster.combatants().items()}
    own_cards = _cards_by_owner(ctx)
    potential_rows = ctx.client.rows(POTENTIAL_NODE_TABLE)
    sift_faces = _CachedSift("sift-faces", _face_art(ctx), match_cache)
    pieces = images.PieceMatcher(_piece_art(REPO_ROOT / PIECE_DIR))
    sift_cards = _CachedSift("sift-cards", _card_art(), match_cache, query_size=images.CARD_RENDER_SIZE, query_box=images.CARD_ART_WINDOW)
    shared_cards = _shared_cards()
    card_names = _card_names(ctx, shared_cards)
    variants_of = lru_cache(maxsize=None)(partial(epiphany.variants, ctx))
    text_cache_path = cache / CARD_TEXT_CACHE
    text_cache = _load_cache(text_cache_path)
    title_cache_path = cache / CARD_TITLE_CACHE
    title_cache = _load_cache(title_cache_path)
    titles = _TitleCards(card_names, title_cache)
    sift_wide = _CachedSift("sift-wide", lambda: _wide_card_art(ctx), match_cache, query_size=images.CARD_RENDER_SIZE, query_box=images.CARD_ART_WINDOW)
    read_text = lambda data: card_text.read_card_text(data, text_cache)
    decks = _DeckPictures()
    issues: list[Issue] = []
    section_fixes = _section_fixes(overrides.directives.get("_sections", {}), issues)
    files: dict[Path, bytes] = {}
    new_files: dict[Path, bytes] = {}
    guides: list[tuple[str, str, dict]] = []
    skipped: list[str] = []
    rated_misses: dict[str, list[str]] = {}
    guesses: dict[str, list[str]] = {key: [] for key in guides_qc.GUESSES}

    for tab_name, gid in tabs(fetcher.text(HTMLVIEW_URL)):
        res_id = tab_ids[tab_name] if tab_name in tab_ids else names.get(_normalise(tab_name.split("/")[0]))
        if res_id is None:
            skipped.append(tab_name)
            continue
        name = roster.combatants()[res_id]["name"]
        grid = parse_grid(fetcher.text(TAB_URL.format(gid=gid)))
        illustrations, card_ids = _card_candidates(ctx, own_cards.get(str(res_id), []))
        cards = _CachedCards(illustrations, card_ids, match_cache)
        guide_slug = slug(name, _SLUG_MAX_LENGTH)
        builder = _GuideBuilder(ctx, downloads, faces, sift_faces, cards, sift_cards, card_names, shared_cards, variants_of, decks, overrides, labels, tab_name, guide_slug,
                               titles, sift_wide, read_text, pieces)
        guide = {
            "charResId": res_id,
            "name": name,
            "source": {"url": EDIT_URL.format(gid=gid), "label": {"en": SOURCE_LABEL}},
        }
        builder.icons = potential_overlay.variant_icons(potential_rows, str(res_id))
        sections, updated = builder.sections(grid)
        if updated:
            guide["updated"] = updated
        guide["sections"] = _pages(sections, section_fixes.get(tab_name, {}))
        guides.append((guide_slug, name, guide))
        rated_misses[name] = builder.rated_misses
        # Written every run like the guide itself, so a tree the author redraws replaces the old one.
        for file_name, download in builder.pictures.items():
            files[POTENTIALS_DIR / file_name] = webp(io.BytesIO(download.data), quality=POTENTIALS_QUALITY)
        for file_name, data in builder.trees.items():
            files[POTENTIALS_DIR / file_name] = data
        for file_name, download in builder.strips.items():
            if (path := IMAGES_DIR / file_name) not in new_files and wanted(ctx, path):
                new_files[path] = webp(io.BytesIO(download.data), quality=IMAGE_QUALITY)
        guesses["dropped_icons"].extend(builder.dropped_icons)
        guesses["filled_pictures"].extend(builder.filled)
        guesses["positional_notes"].extend(f"{tab_name}: {line}" for line in builder.positional_notes)

    # Deck cards are resolved only now, so an exact copy can come from any tab's rated rows.
    unknown_epiphanies: dict[str, _Picture] = {}
    for card, download, ref in decks.pending:
        if not _resolve_deck_card(card, download, ref, decks, overrides.entries, read_text, variants_of):
            _add_unknown_epiphany(unknown_epiphanies, download, ref)
    for guide_slug, _, guide in guides:
        files[DATA_DIR / f"{guide_slug}.guide.json"] = json_bytes(guide)
    found = guides_qc.collect(guides, variants_of, rated_misses, guesses)

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
    (cache / QC_REPORT).write_bytes(guides_qc.report(found))
    print(guides_qc.summary(found), flush=True)
    match_cache_path.write_bytes(json_bytes(dict(sorted(match_cache.items()))))
    text_cache_path.write_bytes(json_bytes(dict(sorted(text_cache.items()))))
    title_cache_path.write_bytes(json_bytes(dict(sorted(title_cache.items()))))
    fetcher.prune()
    files[CONTENT_PATH] = _content_module(sorted(((guide_slug, name) for guide_slug, name, _ in guides), key=lambda guide: guide[1].casefold()))
    return TargetResult(files, f"{len(guides)} guides, {len(new_files)} image(s) to add", issues, new_files=new_files)


def _load_cache(path: Path) -> dict[str, str]:
    """
    A cache file from an earlier run.

    Args:
        path: The JSON file.

    Returns:
        Its contents, or an empty dict when there is no file yet.
    """
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _section_fixes(directive: dict[str, dict[str, str]], issues: list[Issue]) -> dict[str, dict[str, str]]:
    """
    The `_sections` directive without the entries that name no known page.

    Args:
        directive: Tab -> band title -> page id.
        issues: Updated in place with an error for each unknown page id.

    Returns:
        The usable entries, in the same shape.
    """
    fixes: dict[str, dict[str, str]] = {}
    for tab_name, titles in directive.items():
        for title, page_id in titles.items():
            if page_id in _PAGE_IDS:
                fixes.setdefault(tab_name, {})[title] = page_id
            else:
                issues.append(Issue("error", f"{NAME}: `_sections` puts {tab_name!r} band {title!r} on unknown page {page_id!r}"))
    return fixes


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


def _is_icon(picture: Image.Image) -> bool:
    """Whether an unmatched picture is small enough in both directions to be an icon."""
    return picture.width <= ICON_MAX_SIZE and picture.height <= ICON_MAX_SIZE


def _is_strip(picture: Image.Image) -> bool:
    """Whether an unmatched picture is much wider than it is tall."""
    return picture.height > 0 and picture.width / picture.height >= STRIP_MIN_RATIO


def _is_base_card(card_id: str) -> bool:
    """Whether a card id is a base card, not an epiphany copy (`_rsp`) or a potential (`_pot`) of one."""
    return "_rsp" not in card_id and not card_id.endswith("_pot")


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
    for card_id in filter(_is_base_card, own_cards):
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


def _piece_art(directory: Path) -> dict[int, list[Path]]:
    """
    The memory fragment piece art of every set the app lists.

    Args:
        directory: The folder of `item_piece_set_<set>_<slot>.png` files.

    Returns:
        Set id -> its piece images. Sets the app does not list are left out, since an unreleased set can share art with a listed one.
    """
    art: dict[int, list[Path]] = {}
    for path in sorted(directory.glob("*.png")):
        match = _PIECE_FILE.match(path.stem)
        if match and int(match.group(1)) in SETS:
            art.setdefault(int(match.group(1)), []).append(path)
    return art


def _shared_cards() -> dict[str, dict]:
    """
    The deck builder's shared pool of neutral and monster cards, whose ids differ from the client's.

    Returns:
        Card id -> its deck builder entry, with its name, cost and description.
    """
    return {card["id"]: card for card in json.loads((REPO_ROOT / neutral_cards.OUTPUT_PATH).read_text(encoding="utf-8"))}


def _card_names(ctx: Context, shared_cards: dict[str, dict]) -> dict[str, str]:
    """
    The display name of every card a guide can list.

    Args:
        ctx: The run context.
        shared_cards: The deck builder's shared pool, from `_shared_cards`.

    Returns:
        Card id -> name, for character cards and for the shared pool.
    """
    names = {card_id: ctx.text(name, sentences=False) for card_id in ctx.client.cards if (name := ctx.resolver.card_name(card_id))}
    names.update({card_id: card["name"] for card_id, card in shared_cards.items()})
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
            candidates: Key -> its images, or a function that returns them, which is not called until the first picture is matched.
            cache: "<picture sha1>:<pool>:<candidates and settings sha1>" -> key, or "" for no match. Updated in place.
            options: Passed on to `images.SiftMatcher`.
        """
        self.pool = pool
        self.cache = cache
        self.options = options
        self._candidates = candidates
        self._matcher: images.SiftMatcher | None = None

    @cached_property
    def candidates(self) -> dict[str, list[Path]]:
        """The pool's candidates, gathered on first use."""
        return self._candidates() if callable(self._candidates) else self._candidates

    @cached_property
    def signature(self) -> str:
        """Names the candidates and settings, so tuning a threshold re-matches every picture."""
        settings = sorted((name, value) for name, value in vars(images).items() if name.startswith("SIFT_"))
        return hashlib.sha1(f"{sorted(self.candidates)}{settings}{sorted(self.options.items())}".encode("utf-8")).hexdigest()[:12]

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


class _TitleCards:
    """Identifies a card render by reading the name on its title bar and matching it to a card name."""

    def __init__(self, card_names: dict[str, str], cache: dict[str, str]):
        """
        Args:
            card_names: Card id -> display name.
            cache: sha1 of the picture -> its title, from earlier runs. Updated in place.
        """
        self.cache = cache
        # Name (letters only) -> the base ids of the cards with it. An epiphany's id counts as its base card.
        self._by_name: dict[str, set[str]] = {}
        for card_id, name in card_names.items():
            base = _EPIPHANY_ID.sub("", card_id)
            if _is_base_card(base) and (key := _title_key(name)):
                self._by_name.setdefault(key, set()).add(base)
        self._names = list(self._by_name)
        # Title (letters only) -> the ids of the closest card name and how close it is, remembered across pictures.
        self._found: dict[str, tuple[set[str], float]] = {}

    def match(self, data: bytes, own: set[str]) -> tuple[str | None, float]:
        """
        The base card a render's title names, and how closely the title matches the card's name.

        Args:
            data: The picture file.
            own: The base card ids of the guide's character, which win when several cards share the name.

        Returns:
            The card id and the match ratio from 0 to 1, or (None, 0.0) when the title is unreadable, not close to any card name, or shared by cards
            nothing can tell apart.
        """
        title = _title_key(card_text.read_card_title(data, self.cache))
        if len(title) < _TITLE_MIN_LETTERS:
            return None, 0.0
        if title not in self._found:
            close = difflib.get_close_matches(title, self._names, n=1, cutoff=_TITLE_CLOSENESS)
            self._found[title] = (self._by_name[close[0]], difflib.SequenceMatcher(None, title, close[0]).ratio()) if close else (set(), 0.0)
        found, ratio = self._found[title]
        ids = (found & own) or found
        return (next(iter(ids)), ratio) if len(ids) == 1 else (None, 0.0)

    def card_id(self, data: bytes, own: set[str], min_ratio: float = _TITLE_CLOSENESS) -> str | None:
        """
        The card a render's title names, when the title is at least `min_ratio` close to its name.

        Args:
            data: The picture file.
            own: The base card ids of the guide's character.
            min_ratio: How close the read title must be to the card's name, from 0 to 1.

        Returns:
            The card id, or None when there is no such card.
        """
        card_id, ratio = self.match(data, own)
        return card_id if ratio >= min_ratio else None


def _title_key(text: str) -> str:
    """A card title as lower-case letters only, without a bracketed epiphany name, for matching read titles to card names."""
    return card_text._letters(re.sub(r"\(.*?\)", "", text))


def _wide_card_art(ctx: Context) -> dict[str, list[Path]]:
    """
    Every card illustration in the client, one entry per distinct image.

    Args:
        ctx: The run context.

    Returns:
        Base card id -> its illustration, for the first card that uses each.
    """
    illustrations, card_ids = _card_candidates(ctx, sorted(ctx.client.cards))
    return {card_ids[name]: [path] for name, path in illustrations.items()}


class _GuideBuilder:
    """Turns one tab's cell grid into guide sections."""

    def __init__(self, ctx: Context, downloads: _Downloads, faces: images.FaceMatcher, sift_faces: _CachedSift, cards: _CachedCards,
                 sift_cards: _CachedSift, card_names: dict[str, str], shared_cards: dict[str, dict], variants_of, decks: _DeckPictures, overrides: Overrides,
                 labels: _PictureLabels, tab_name: str, guide_slug: str, titles: _TitleCards, sift_wide: _CachedSift, read_text,
                 pieces: images.PieceMatcher | None = None):
        """
        Args:
            ctx: The run context.
            downloads: The sheet's pictures, decoded once per run.
            faces: Identifies face portraits by hash.
            sift_faces: Identifies the face portraits the hash misses.
            cards: Identifies this character's card renders.
            sift_cards: Identifies the card renders `cards` misses, among every card in the deck builder.
            card_names: Card id -> display name, written next to each listed card.
            shared_cards: The deck builder's neutral and monster cards, which give those cards their cost and text.
            variants_of: Card id -> its `epiphany.variants`, shared by every tab.
            decks: Collects rated pictures and the deck cards to resolve once every tab is read.
            overrides: The guides overrides, whose entries can label one cell as "<tab>!<cell>".
            labels: Labels by picture, which also collect what nothing identified.
            tab_name: The sheet tab, used in cell override keys and references.
            guide_slug: The guide's id, which names its potentials picture.
            titles: Reads a card render's title bar and finds the card it names.
            sift_wide: SIFT over every card illustration in the client, for the renders nothing else identified.
            read_text: Picture bytes -> its OCR text, which reads the epiphany of a repeated card in a rated row.
            pieces: Identifies the memory fragment piece pictures, which the face matchers miss.
        """
        self.ctx = ctx
        self.downloads = downloads
        self.faces = faces
        self.sift_faces = sift_faces
        self.cards = cards
        self.sift_cards = sift_cards
        self.card_names = card_names
        self.shared_cards = shared_cards
        self.variants_of = variants_of
        self.decks = decks
        self.overrides = overrides
        self.labels = labels
        self.tab_name = tab_name
        self.guide_slug = guide_slug
        self.titles = titles
        self.sift_wide = sift_wide
        self.read_text = read_text
        self.pieces = pieces
        # File name -> picture, for the pictures this guide ships (its potentials tree).
        self.pictures: dict[str, _Download] = {}
        # File name -> encoded WebP, for the guide's clean potentials tree with the author's ring colours drawn on it.
        self.trees: dict[str, bytes] = {}
        # Node label -> icon name for the character's two stat nodes, set by `build`.
        self.icons: dict[str, str] = {}
        # File name -> picture, for the wide strips this guide shows as image blocks.
        self.strips: dict[str, _Download] = {}
        # For the QC report: the cells of dropped icons, of pictures given a card by the run they sit in, and the note lines placed by their number.
        self.dropped_icons: list[str] = []
        self.filled: list[str] = []
        self.positional_notes: list[str] = []
        # Cells of pictures in rated rows that nothing identified, for the QC report.
        self.rated_misses: list[str] = []
        # The tab's `layout`, set by `sections`, which keeps a cached picture from being served for a cell it has moved out of.
        self._layout = ""

    def _picture_key(self, cell: Cell, index: int) -> str:
        """
        What names one of a cell's pictures in the download cache, since its address changes every run.

        Args:
            cell: The cell holding the picture.
            index: Which of the cell's pictures it is.

        Returns:
            A key such as "Olga!B3#0@<layout>".
        """
        return f"{self.tab_name}!{cell.ref}#{index}@{self._layout}"

    def sections(self, grid: dict[tuple[int, int], Cell]) -> tuple[list[dict], str | None]:
        """
        Every section of the guide, one per band of rows.

        Args:
            grid: The tab's cells.

        Returns:
            The sections, in sheet order, without empty ones, and the sheet's edit date if it has one.
        """
        self._layout = layout(grid)
        sections: list[dict] = []
        for band in _bands(grid):
            blocks, band = self._potentials(band)
            title = POTENTIALS_TITLE if blocks else None
            for panel in _panels(band):
                panel_title, panel_blocks, title_shown = self._panel(panel)
                if title is None:
                    title = panel_title
                elif panel_title and not title_shown:
                    # A later panel's heading would otherwise be lost, so it leads that panel's blocks instead.
                    table = bool(panel_blocks) and panel_blocks[0]["type"] == "table"
                    panel_blocks.insert(0, {"type": "heading", "text": self._text(panel_title)} if table else self._prose(panel_title))
                blocks.extend(panel_blocks)
            blocks = [self._deck_or_list(block) if block["type"] == "card-list" else block for block in _attach_notes(blocks, self.positional_notes)]
            if not blocks:
                continue
            sections.append({"title": self.ctx.text(title, soften=True, sentences=False) if title else None, "blocks": blocks})
        return _tidy_sections(sections)

    def _potentials(self, band: list[Cell]) -> tuple[list[dict], list[Cell]]:
        """
        The potentials block, when the band holds the colour legend.

        Args:
            band: The band's cells.

        Returns:
            The potentials block followed by any extra legend lines as prose, and the cells it did not use. No blocks and the
            whole band when there is no legend. The tree is the picture in the legend's panel, on its row or the one above.
        """
        legend = next((cell for cell in band if _LEGEND.match(cell.text)), None)
        if legend is None:
            return [], band
        tree = next((cell for cell in band if cell.images and _panel_index(cell.col) == _panel_index(legend.col) and legend.row - 1 <= cell.row <= legend.row), None)
        ego = next((cell for cell in band if _EGO_LEVEL.search(cell.text)), None)
        colours, extra = [], []
        for line in legend.text.split("\n"):
            if match := _LEGEND_LINE.match(line):
                colours.append({"colour": match.group(1).lower(), "text": self._text(match.group(2))})
            elif line.strip():
                extra.append(line.strip())
        # Levels are numbered in the order they are written, as some tabs label E5 as "E3".
        notes = _EGO_LEVEL.split(ego.text) if ego else [""]
        image = f"{self.guide_slug}.webp" if tree else None
        if tree:
            self.pictures[image] = self.downloads.get(tree.images[0], self._picture_key(tree, 0))
        tree_image, coloured = self._tree(self.pictures[image].picture if tree else None)
        bold = _bold_levels(ego) if ego else []
        block = {"type": "potentials", "image": image, "treeImage": tree_image, "coloured": coloured, "legend": colours,
                 "ego": [{"level": level, "text": self._text(note.strip()), **({"bold": True} if level - 1 < len(bold) and bold[level - 1] else {})}
                         for level, note in enumerate(notes[1:], 1)]}
        if notes[0].strip():
            extra.append(notes[0].strip())
        used = {cell.ref for cell in (legend, tree, ego) if cell}
        rest = [cell for cell in band if cell.ref not in used and not (_is_label_row([cell.text]) and _POTENTIALS_HEADING.search(cell.text))]
        return [block, *([self._prose("\n".join(extra))] if extra else [])], rest

    def _tree(self, author: Image.Image | None) -> tuple[str, bool]:
        """
        Draw this guide's clean potentials tree from the author's picture.

        Args:
            author: The author's tree picture, or None when the tab has none.

        Returns:
            The file name of the tree, which is kept in `trees`, and whether the author's ring colours were read.
        """
        picture, coloured = potential_overlay.build(author, self.icons)
        name = f"{self.guide_slug}-tree.webp"
        buffer = io.BytesIO()
        picture.save(buffer, "WEBP", quality=POTENTIALS_QUALITY)
        self.trees[name] = buffer.getvalue()
        return name, coloured

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
        if table := self._table(rows):
            return table
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
                if all(block["type"] in ("image", "set-list") for block in new_blocks):
                    # Text beside pictures that are not cards or faces, such as a relic's substats note next to its set icons.
                    for picture_row in rows[index:index + consumed]:
                        if any(cell.images for cell in picture_row):
                            blocks.extend(self._prose(cell.text) for cell in picture_row if cell.text)
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

    def _table(self, rows: list[list[Cell]]) -> tuple[str | None, list[dict], bool] | None:
        """
        A panel laid out as a table, such as a Desire Synergy list: an optional heading row, then rows of text that each end in a rating.

        Args:
            rows: The panel's rows.

        Returns:
            The heading and the table block, as `_panel` returns them, or None when the panel is not such a table. Its columns are
            the panel's text columns, and a row with nothing in a column gets an empty cell there.
        """
        if any(cell.images for row in rows for cell in row):
            return None
        rows = [texts for texts in ([cell for cell in row if cell.text] for row in rows) if texts]
        heading = " | ".join(cell.text for cell in rows[0]) if rows and _is_label_row([cell.text for cell in rows[0]]) else None
        body = rows[1:] if heading else rows
        if len(body) < 2 or not all(len(row) >= 2 and _RATING.match(row[-1].text) and not any(_RATING.match(cell.text) for cell in row[:-1]) for row in body):
            return None
        columns = sorted({cell.col for row in body for cell in row[:-1]})
        table = []
        for row in body:
            texts = {cell.col: cell.text for cell in row[:-1]}
            table.append({"cells": [self._text(texts[col]) if col in texts else {"en": ""} for col in columns], "rating": row[-1].text})
        return heading, [{"type": "table", "rows": table}], False

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
        strips: list[dict] = []
        face_rows: list[list[tuple[int, int]]] = []
        piece_rows: list[list[tuple[int, int]]] = []
        for row in rows[start:end]:
            # A card nothing identified stays in the row as a gap (cardId None), so its neighbours keep their places.
            row_cards: list[dict] = []
            face_row: list[tuple[int, int]] = []
            piece_row: list[tuple[int, int]] = []
            for cell in row:
                ref = f"{self.tab_name}!{cell.ref}"
                for index, url in enumerate(cell.images):
                    download = self.downloads.get(url, self._picture_key(cell, index))
                    kind = download.kind
                    found = {} if self.labels.empty else self.labels.find(download.hash)
                    label = {**found, **self.overrides.entries.get(ref, {})}
                    if label.get("skip"):
                        continue
                    if "setId" in label:
                        piece_row.append((cell.col, label["setId"]))
                    elif "charResId" in label or (kind == "face" and "cardId" not in label):
                        res_id = label.get("charResId") or self._face(download)
                        set_id = self._piece(download) if res_id is None and "charResId" not in label else None
                        if set_id is not None:
                            piece_row.append((cell.col, set_id))
                        elif res_id is None:
                            self._miss(download, kind, ref, bool(ratings))
                        else:
                            face_row.append((cell.col, res_id))
                    elif "cardId" in label or kind == "card":
                        card_id = label.get("cardId") or self._card(download)
                        if card_id is None:
                            self._miss(download, kind, ref, bool(ratings))
                        row_cards.append({"cardId": card_id, "col": cell.col, "picture": (download, ref), **{key: label[key] for key in ("name", "persona") if key in label}})
                    elif _is_icon(download.picture):
                        # An icon-sized picture that is not square, such as a piece the sheet stretched a little, may still be a piece.
                        if (set_id := self._piece(download)) is not None:
                            piece_row.append((cell.col, set_id))
                        else:
                            self.dropped_icons.append(ref)
                    elif _is_strip(download.picture):
                        strips.append({"type": "image", "image": self._strip_name(download)})
                    else:
                        # Banners and the like. Listed for review so they can be labelled or skipped.
                        self._miss(download, kind, ref, bool(ratings))
            if ratings:
                _fill_unread(row_cards, self.variants_of, self.filled)
            row_cards = _number_runs(row_cards)
            cards.extend(self._settle_repeats(row_cards, ratings) if ratings else row_cards)
            if face_row:
                face_rows.append(face_row)
            if piece_row:
                piece_rows.append(piece_row)

        blocks = []
        named = False
        if cards:
            blocks.append(self._card_list(cards, ratings))
        if face_rows:
            face_block, named = self._face_block(face_rows, ratings, names)
            blocks.append(face_block)
        if piece_rows:
            # The label row above names the first row of pieces. The sets of any later row have no labels of their own.
            blocks.extend(_piece_block(row, names if index == 0 else {}) for index, row in enumerate(piece_rows))
            named = named or bool(names)
        blocks.extend(strips)
        return consumed, blocks, named

    def _strip_name(self, download: _Download) -> str:
        """
        The file name a wide strip is shown under, which the guide ships.

        Args:
            download: The sheet's picture.

        Returns:
            The name, from the picture's hash.
        """
        name = f"{download.sha1[:16]}.webp"
        self.strips[name] = download
        return name

    @cached_property
    def _own_cards(self) -> set[str]:
        """The base card ids of this guide's character."""
        return set(self.cards.card_ids.values())

    def _card(self, download: _Download) -> str | None:
        """
        The card a render shows.

        Args:
            download: The sheet's picture.

        Returns:
            The art match, from this character's cards and then the deck builder's card art. A clearly read title replaces it only when it names a
            different base card, as a copy of another card's art is the render with a changed title. Without an art match, the title and then the
            art of every card in the client. None when none is clear.
        """
        art = self.cards.card_id(download.picture, download.data) or self.sift_cards.match(download.picture, download.data)
        title, ratio = self.titles.match(download.data, self._own_cards)
        if art is None:
            return title or self.sift_wide.match(download.picture, download.data)
        return title if title and ratio >= _TITLE_TRUSTED and title != _EPIPHANY_ID.sub("", art) else art

    def _settle_repeats(self, row_cards: list[dict], ratings: dict[int, str]) -> list[dict]:
        """
        Pictures of one card side by side in a rated row, which are not a whole run of its epiphanies, as one card or a partial ladder.

        Args:
            row_cards: One row's identified cards in order, each with its `epiphany` position.
            ratings: column -> rating text.

        Returns:
            The cards. Each such run gets the epiphany levels its pictures show, read the way deck cards are, so they fold into a ladder.
            When they cannot be read, equally rated pictures become one card with a `count`. Otherwise the run is left as it is. Persona
            copies are always left apart, as each shows its own engravings. A lone picture gets the level its cell override gives.
        """
        settled: list[dict] = []
        for (card_id, _), group in groupby(row_cards, key=lambda card: (card["cardId"], card.get("persona"))):
            run = list(group)
            entry = self.overrides.entries.get(run[0]["picture"][1], {}) if len(run) == 1 and run[0]["picture"] else {}
            if "epiphany" in entry:
                run[0]["level"] = entry["epiphany"]
            if len(run) == 1 or card_id == guides_qc.PERSONA_CARD or len(run) == len(self.variants_of(card_id)) - 1:
                settled.extend(run)
                continue
            levels = self._read_levels(run)
            if levels:
                for card, level in zip(run, levels):
                    card["level"] = level
                settled.extend(sorted(run, key=lambda card: card["level"]))
            elif len({ratings.get(card["col"]) for card in run}) == 1:
                settled.append({**run[0], "count": len(run)})
            else:
                settled.extend(run)
        return settled

    def _read_levels(self, run: list[dict]) -> list[int] | None:
        """
        The epiphany level each picture of one card shows.

        Args:
            run: Pictures of one card.

        Returns:
            Their levels, 0 for the base card, or None when any cannot be read or two show the same level.
        """
        if not self.variants_of(run[0]["cardId"]):
            return None
        levels = []
        for card in run:
            download, ref = card["picture"]
            found = _find_epiphany(card["cardId"], download, ref, self.decks, self.overrides.entries, self.read_text, self.variants_of)
            if found is None:
                return None
            levels.append(found[0].level)
        return levels if len(set(levels)) == len(levels) else None

    def _miss(self, download: _Download, kind: str, ref: str, rated: bool) -> None:
        """
        Record a picture nothing identified.

        Args:
            download: The sheet's picture.
            kind: "face", "card" or "other".
            ref: Its cell, such as "Tenebria!B11".
            rated: Whether it sits in a row with ratings under it.
        """
        self.labels.unidentify(download.hash, download.data, kind, ref)
        if rated:
            self.rated_misses.append(ref)

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

    def _piece(self, download: _Download) -> int | None:
        """
        The memory fragment set a piece picture shows.

        Args:
            download: The sheet's picture.

        Returns:
            The set id, or None when there is no piece matcher or no set is a clear match.
        """
        return self.pieces.match(download.picture) if self.pieces else None

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
            if card.get("name") or card_id in self.card_names:
                item["name"] = card.get("name") or self.card_names[card_id]
            if "persona" in card:
                item["persona"] = card["persona"]
            if card_id in self.ctx.client.cards:
                item["cost"] = epiphany.printed_cost(self.ctx, card_id)
            elif shared := self.shared_cards.get(card_id):
                item["cost"] = shared["cost"]
            item["note"] = {"en": ""}
            if card["col"] in ratings:
                item["rating"] = ratings[card["col"]]
            if "count" in card:
                item["count"] = card["count"]
            if "level" in card:
                item["level"] = card["level"]
            elif card_id in variants:
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
            # Shared-pool cards have no epiphanies and use the pool's text. A client card with no epiphanies shows its own base text.
            card_id = card["cardId"]
            if shared := self.shared_cards.get(card_id):
                card["text"] = {"en": shared["description"]}
            elif card_id in self.ctx.client.cards and not self.variants_of(card_id):
                card["text"] = {"en": epiphany.base_text(self.ctx, card_id)}
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
            groups = [{"title": self._text(names[col]), "members": self._members(res_id for row in face_rows for c, res_id in row if c == col)}
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

    def _text(self, text: str) -> dict:
        """Sheet text as localized guide text."""
        return {"en": self.ctx.text(text, soften=True, sentences=False)}

    def _prose(self, text: str) -> dict:
        return {"type": "prose", "body": self._text(text)}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Grid helpers


def _tidy_sections(sections: list[dict]) -> tuple[list[dict], str | None]:
    """
    Sections as the page shows them.

    Args:
        sections: Each band's title (None when it has none) and blocks.

    Returns:
        The sections, and the sheet's edit date. The "Last Edit" section is dropped for that date. An untitled section is
        named for what it holds, and one-line lists of sets (as a title or a prose line) become set cards.
    """
    tidied: list[dict] = []
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
            # Piece pictures under the title's labels already make that set-list, so it is moved to the front rather than shown twice.
            labels = [item["label"] for item in title_sets]
            shown = next((block for block in blocks if block["type"] == "set-list" and [item["label"] for item in block["items"]] == labels), None)
            if shown:
                blocks.remove(shown)
            blocks.insert(0, shown or {"type": "set-list", "items": title_sets})
        tidied.append({"title": {"en": title}, "blocks": blocks})
    return tidied, updated


def _pages(sections: list[dict], fixes: dict[str, str]) -> list[dict]:
    """
    The guide's sections sorted into the standard pages.

    Args:
        sections: The tidied sections, in sheet order.
        fixes: Band title -> page id, from the `_sections` directive, for a band the rules put on the wrong page.

    Returns:
        Every page in `PAGES`, then the extras page when it has anything. Each band's title leads its blocks as a heading, unless it
        only repeats the page or is already shown as set cards. A page with no bands has no blocks and is marked missing.
    """
    partners_at = next((index for index, section in enumerate(sections) if any(block["type"] == "partner-list" for block in section["blocks"])), len(sections))
    grouped: dict[str, list[dict]] = {page_id: [] for page_id in _PAGE_IDS}
    for index, section in enumerate(sections):
        page_id = fixes.get(section["title"]["en"]) or _page_of(section, index, partners_at)
        heading = [] if page_id in _UNTITLED_PAGES or set_line(section["title"]["en"]) else [{"type": "heading", "text": section["title"]}]
        grouped[page_id].extend([*heading, *section["blocks"]])
    pages = []
    for page_id, title in [*PAGES, EXTRAS_PAGE]:
        blocks = grouped[page_id]
        if blocks or page_id != EXTRAS_PAGE[0]:
            pages.append({"id": page_id, "title": {"en": title}, "blocks": blocks, **({} if blocks else {"missing": True})})
    return pages


def _page_of(section: dict, index: int, partners_at: int) -> str:
    """
    The page a band belongs on, from what it holds and where it sits.

    Args:
        section: The tidied section.
        index: Its position among the guide's sections.
        partners_at: The position of the first partners band, or the section count when there is none.

    Returns:
        The page id. Bands after the partners that are not relics, potentials, ratings or teams are extras. Before the partners,
        the first band and notes are the playstyle, and bands with decks are the decks.
    """
    types = [block["type"] for block in section["blocks"]]
    if "potentials" in types:
        return "potentials"
    if section["title"]["en"].casefold() == "card ratings":
        return "card-ratings"
    if "partner-list" in types:
        return "partners"
    if types and types[0] == "set-list":
        return "relics"
    if types and types.count("team-grid") * 2 >= len(types):
        return "teams"
    if index > partners_at:
        return EXTRAS_PAGE[0]
    if index == 0 or _PLAYSTYLE_TITLE.search(section["title"]["en"]):
        return "playstyle"
    return "decks" if {"deck", "rating-list"} & set(types) else "playstyle"


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


def _piece_block(pieces: list[tuple[int, int]], names: dict[int, str]) -> dict:
    """
    A loadout's piece pictures as a set-list, each set under the label the sheet gives its column.

    Args:
        pieces: (column, set id) per identified piece picture.
        names: column -> the label above that column. A labelled column with no identified piece stays in the list as a bare label.

    Returns:
        The set-list block. A piece with no label above it takes its set's name.
    """
    sets = dict(pieces)
    items = [set_item(names.get(col) or SETS[sets[col]]["name"], sets[col]) if col in sets else {"label": names[col]} for col in sorted({*sets, *names})]
    return {"type": "set-list", "items": items}


def _set_block(block: dict) -> dict:
    """A prose line listing sets as a set-list block, any other block as it is."""
    items = set_line(block["body"]["en"]) if block["type"] == "prose" else None
    return {"type": "set-list", "items": items} if items else block


def _bold_levels(cell: Cell) -> list[bool]:
    """
    Which of an ego manifestation cell's levels the sheet writes in bold.

    Args:
        cell: The cell, whose levels start at "E1:" style lines.

    Returns:
        One flag per level in the order written. A level is bold when more than `_BOLD_SHARE` of its non-space characters are bold.
    """
    matches = list(_EGO_LEVEL.finditer(cell.text))
    flags = []
    for match, following in zip(matches, [*matches[1:], None]):
        start, end = match.end(), following.start() if following else len(cell.text)
        total = _letters_of(cell.text[start:end])
        marked = sum(_letters_of(cell.text[max(first, start):min(last, end)]) for first, last in cell.bold if first < end and last > start)
        flags.append(total > 0 and marked / total > _BOLD_SHARE)
    return flags


def _letters_of(text: str) -> int:
    """How many characters of the text are not whitespace."""
    return len("".join(text.split()))


def _number_runs(row_cards: list[dict]) -> list[dict]:
    """
    Number a row's cards by their place in a run of the same card, which is the epiphany level a whole rated run shows.

    Args:
        row_cards: One row's cards in order. A card nothing identified (cardId None) ends the run before it and is dropped.

    Returns:
        The identified cards, each with its `epiphany` position, 1 for a card that does not follow the same card.
    """
    numbered: list[dict] = []
    for card_id, run in groupby(row_cards, key=lambda card: card["cardId"]):
        if card_id is not None:
            numbered.extend({**card, "epiphany": position} for position, card in enumerate(run, 1))
    return numbered


def _fill_unread(row_cards: list[dict], variants_of, filled: list[str] | None = None) -> None:
    """
    Give the pictures nothing identified (cardId None) the card they sit in a run of, when that makes the run whole.

    Args:
        row_cards: One row's cards in order. Updated in place.
        variants_of: Card id -> its `epiphany.variants`, whose length less the base card is the length of a whole run.
        filled: Collects the cell of each picture given a card, for the QC report. Not collected when None.
    """
    # Each run of one card id (or of unread pictures) as [card id, how many pictures].
    runs = [[card_id, len(list(run))] for card_id, run in groupby(row_cards, key=lambda card: card["cardId"])]
    start = 0
    for index, (card_id, size) in enumerate(runs):
        end = start + size
        if card_id is None:
            left = runs[index - 1][0] if index else None
            right = runs[index + 1][0] if index + 1 < len(runs) else None
            fits = [
                candidate for candidate in dict.fromkeys([left, right])
                if candidate is not None and _run_total(runs, index - 1, -1, candidate) + size + _run_total(runs, index + 1, 1, candidate) == len(variants_of(candidate)) - 1
            ]
            if len(fits) == 1:
                runs[index][0] = fits[0]
                for card in row_cards[start:end]:
                    card["cardId"] = fits[0]
                    if filled is not None and card.get("picture"):
                        filled.append(card["picture"][1])
        start = end


def _run_total(runs: list[list], index: int, step: int, card_id: str) -> int:
    """How many pictures the runs from `index` in the direction of `step` hold, while they are this card."""
    total = 0
    while 0 <= index < len(runs) and runs[index][0] == card_id:
        total += runs[index][1]
        index += step
    return total


def _complete_runs(cards: list[dict], variants_of) -> set[str]:
    """
    The cards whose rated renders are one whole run of their epiphany levels, so each render's position is its level.

    Args:
        cards: Identified cards with their epiphany position in the row.
        variants_of: Card id -> its `epiphany.variants`.

    Returns:
        The card ids whose positions are exactly 1 to their last level. A run that was cut short, restarted or split gives
        no levels, as a wrong level is worse than none. Cards whose level is already known are left out.
    """
    positions: dict[str, list[int]] = {}
    for card in (card for card in cards if "level" not in card):
        positions.setdefault(card["cardId"], []).append(card["epiphany"])
    return {card_id for card_id, found in positions.items() if found == list(range(1, len(variants_of(card_id))))}


def _fold(items: list[dict], variants_of) -> list[dict]:
    """
    Each rated run of one card's renders as one item that lists its epiphanies.

    Args:
        items: Card-list items. Those in a rated run carry their epiphany `level`, by position.
        variants_of: Card id -> its `epiphany.variants`.

    Returns:
        The items, each run folded into one item whose `epiphanies` hold every level's name, cost, rating and note. A rated base
        copy (level 0) is that item, keeping its own rating, whether it comes before the run or after it. A card with no variants
        is kept as it is, without its level.
    """
    folded: list[dict] = []
    for item in items:
        item = dict(item)
        level = item.pop("level", None)
        if level == 0 and variants_of(item["cardId"]):
            last = folded[-1] if folded else None
            if last and last["cardId"] == item["cardId"] and last.get("epiphanies") and "rating" not in last:
                # A base copy on the row under its ladder rates the ladder's card.
                last.update({key: item[key] for key in ("rating", "cost") if key in item})
            else:
                folded.append({**item, "epiphanies": []})
            continue
        variant = next((variant for variant in variants_of(item["cardId"]) if variant.level == level), None) if level else None
        if variant is None:
            folded.append(item)
            continue
        entry = {"level": level, "name": variant.name, "cost": variant.cost}
        if "rating" in item:
            entry["rating"] = item["rating"]
        entry["note"] = {"en": ""}
        last = folded[-1] if folded else None
        if last and last["cardId"] == item["cardId"] and "epiphanies" in last and all(entry["level"] < level for entry in last["epiphanies"]):
            last["epiphanies"].append(entry)
        else:
            head = {key: item[key] for key in ("cardId", "name") if key in item}
            folded.append({**head, "note": {"en": ""}, "epiphanies": [entry]})
    for item in folded:
        if item.get("epiphanies") == []:
            del item["epiphanies"]
    return folded


def _line_target(line: str, items: list[dict], positional: dict | None, by_position: list[str] | None) -> tuple[list[dict], str] | None:
    """
    The items, or epiphanies of them, that a "Name: note" prose line is for.

    Args:
        line: The prose line.
        items: The listed cards or partners.
        positional: The one card whose ladder a numbered label may pick by its number alone.
        by_position: Collects the lines that were placed only by their number, for the QC report. Not collected when None.

    Returns:
        The targets and the line's note text, or None when the line names none of the items.
    """
    for match in filter(None, (_NOTE_LINE.match(line), _NUMBERED_NOTE_LINE.match(line))):
        targets = _note_targets(items, match.group(1))
        if not targets and positional:
            targets = _note_targets(items, match.group(1), positional)
            if targets and by_position is not None:
                by_position.append(line.strip())
        if targets:
            return targets, match.group(2)
    return None


def _attach_notes(blocks: list[dict], by_position: list[str] | None = None) -> list[dict]:
    """
    "Name: note" prose lines moved onto the card or partner they name.

    Args:
        blocks: A section's blocks.
        by_position: Collects the lines placed only by their level number, for the QC report. Not collected when None.

    Returns:
        The blocks. Prose straight after a card-list or partner-list gives up each line that names one of its items, and the
        rest stays in order. A list of rated copies of one card takes the labelled lines in order instead, when there is one
        for each copy. A prose block left empty is dropped.
    """
    kept: list[dict] = []
    for block in blocks:
        previous = kept[-1] if kept else None
        if block["type"] != "prose" or not previous or previous["type"] not in ("card-list", "partner-list"):
            kept.append(block)
            continue
        rest = []
        # A card list of one ladder takes any numbered line by its level, as the sheet's own label may be misspelled or shortened.
        ladders = [item for item in previous["items"] if item.get("epiphanies")]
        lines = block["body"]["en"].split("\n")
        labelled = [i for i, line in enumerate(lines) if _NOTE_LINE.match(line)] if _copies_in_order(previous) else []
        if labelled and len(labelled) == len(previous["items"]):
            # Copies such as Personas cannot be told apart by name, so the sheet notes each with one labelled line, in the order they are listed.
            for item, i in zip(previous["items"], labelled):
                _add_note(item, lines[i].strip())
            lines = [line for i, line in enumerate(lines) if i not in labelled]
        numbered = sum(1 for line in lines if _SHORT_NUMBERED_LINE.match(line))
        positional = ladders[0] if previous["type"] == "card-list" and len(previous["items"]) == 1 and ladders and numbered >= 2 else None
        for line in lines:
            found = _line_target(line, previous["items"], positional, by_position)
            if found is None:
                rest.append(line)
                continue
            targets, text = found
            for target in targets:
                _add_note(target, text)
        if any(line.strip() for line in rest):
            kept.append({**block, "body": {"en": "\n".join(rest)}})
    return kept


def _copies_in_order(block: dict) -> bool:
    """Whether a block is a card-list of two or more rated copies of one card, Personas or under one name, with no epiphany ladders."""
    items = block["items"] if block["type"] == "card-list" else []
    if len(items) < 2 or len({item["cardId"] for item in items}) > 1 or not all(item.get("rating") and not item.get("epiphanies") for item in items):
        return False
    return items[0]["cardId"] == guides_qc.PERSONA_CARD or len({item.get("name") for item in items}) == 1


def _add_note(target: dict, text: str) -> None:
    """
    Add a line to an item's or epiphany's note.

    Args:
        target: The item or epiphany.
        text: The note line.
    """
    note = target["note"]["en"]
    target["note"] = {"en": f"{note}\n{text}" if note else text}


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
    return {"type": "deck", "cards": [{key: item[key] for key in ("cardId", "name", "cost", "persona") if key in item} for item in block["items"]]}


def _find_epiphany(card_id: str, download: _Download, ref: str, decks: _DeckPictures, overrides: dict[str, dict], read, variants_of) -> tuple[Variant, Extra | None] | None:
    """
    The epiphany a card picture shows and its added divine or common line.

    Args:
        card_id: The card, which has epiphanies.
        download: Its picture.
        ref: Its cell, such as "Rossweisse!C10".
        decks: The rated pictures, for an exact copy.
        overrides: Guides override entries by cell. One can give `epiphany` (0 for the base card) and `divine` or `common`.
        read: Picture bytes -> its OCR text.
        variants_of: Card id -> its `epiphany.variants`.

    Returns:
        The level's variant and the added line, or None when nothing read it clearly.
    """
    variants = {variant.level: variant for variant in variants_of(card_id)}
    entry = overrides.get(ref, {})
    extra = None
    if "epiphany" in entry:
        level = entry["epiphany"]
        extra = _extra(entry.get("divine") or entry.get("common"))
    elif (level := decks.level_of(card_id, download)) is None:
        key = (card_id, download.sha1)
        if key not in decks.matches:
            # The emblem only picks which lines to try. Text alone mixes up divine lines that read alike.
            god = card_text.match_god(download.picture)
            extras = [line for line in epiphany.divine_epiphanies() if line.god == god] if god else epiphany.common_epiphanies()
            decks.matches[key] = card_text.match_epiphany(read(download.data), list(variants.values()), extras)
        match = decks.matches[key]
        if match is None:
            return None
        level, extra = match.level, match.extra
    return (variants[level], extra) if level in variants else None


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
    if not variants_of(card["cardId"]):
        return True
    found = _find_epiphany(card["cardId"], download, ref, decks, overrides, read, variants_of)
    if found is None:
        return False
    variant, extra = found
    card["cost"] = epiphany.card_cost(variant.cost, extra)
    card["epiphany"] = {"level": variant.level, "name": variant.name, "text": {"en": variant.text}}
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


def _name_words(name: str) -> list[str]:
    """A card name split into its words, which are what a note label may name."""
    return [word for word in re.split(r"[\s:]+", name) if word]


def _names_card(base: str, name: str) -> bool:
    """
    Whether a note label's base word stands for a card name.

    Args:
        base: The label without its level number, lower case.
        name: The card's name, lower case.

    Returns:
        True when the base is the name, one of its words, its initials ("OUAT", or "CnR" for "Call & Response"), or within a typo of
        one of its words.
    """
    words = _name_words(name)
    if not base or base == name or base in words:
        return True
    if len(words) > 1 and base == "".join(word[0] for word in words).replace("&", "n"):
        return True
    return len(base) >= 3 and any(difflib.SequenceMatcher(None, base, word).ratio() >= _NOTE_NAME_CLOSENESS for word in words)


def _note_targets(items: list[dict], label: str, positional: dict | None = None) -> list[dict]:
    """
    The items, or epiphanies of them, that a note label names.

    Args:
        items: The listed cards or partners.
        label: The text before the colon, such as "Tassel", "Flow 2", "OUAT 1", "Cresc(endo)" or "Unbound".
        positional: The one card whose ladder a numbered label may pick by its number alone, whatever its words.

    Returns:
        Every epiphany whose game name is the label ("Unbound"), as cards listed together can share one. Else, for a numbered label,
        the card whose name holds the number ("Quest 1"), the epiphany of that level ("Flow 2"), or the card itself for level 0.
        Else the item whose name or a word of it is the label. Empty when nothing fits.
    """
    wanted = _WORD_ENDING.sub(r"\1", label).strip().lower()
    if not wanted:
        return []
    shared = [entry for item in items for entry in item.get("epiphanies", []) if (part := _GAME_NAME_PART.search(entry["name"])) and part.group(1).lower() == wanted]
    if shared:
        return shared
    numbered = _NUMBERED_LABEL.match(wanted)
    if not numbered:
        return next(([item] for item in items if (name := item.get("name", "").lower()) == wanted or wanted in _name_words(name)), [])
    base, number = numbered.groups()
    level = int(number)
    named = [item for item in items if _names_card(base, item.get("name", "").lower())]
    for item in named:
        if number in _name_words(item["name"].lower()):
            return [item]
        found = next((entry for entry in item.get("epiphanies", []) if entry["level"] == level), None)
        if found:
            return [found]
    if level == 0:
        return named[:1] or ([positional] if positional else [])
    return [entry for entry in positional["epiphanies"] if entry["level"] == level][:1] if positional else []


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
        panels.setdefault(_panel_index(cell.col), []).append(cell)
    return [panels[index] for index in sorted(panels)]


def _panel_index(col: int) -> int:
    """Which side-by-side panel a column falls in, counting from 0 at column B."""
    return max(col - 1, 0) // PANEL_WIDTH


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
