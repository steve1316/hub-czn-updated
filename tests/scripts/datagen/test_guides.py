"""
Tests for the Guides import: the sheet's HTML grid, splitting a tab into sections, picture labels and the image matchers.
Everything runs on synthetic inputs, so no network or extracted client is needed.
"""

from __future__ import annotations

import io
import random
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFilter

from api.client_db import client_output_dir, have_client_db, have_client_text
from scripts.datagen import card_text, epiphany, images, naming, set_names
from scripts.datagen.epiphany import Variant
from scripts.datagen.runner import Context
from scripts.datagen.sheet import Cell, Fetcher, column_letters, parse_grid, tabs
from scripts.datagen.targets import guides

TAB_LIST = 'items.push({name: "Tenebria", pageUrl: "x", gid: "484210597"});items.push({name: "Adelheid\\/ADHD", pageUrl: "x", gid: "7"});'

GRID = """
<table><tbody>
<tr><th>1</th><td>Glossary Link</td><td></td><td></td></tr>
<tr><th>2</th><td></td><td></td><td></td></tr>
<tr><th>3</th><td colspan="2">Partners</td><td><img src="https://example/face.png"></td></tr>
<tr><th>4</th><td rowspan="2">Line one<br>Line two</td><td>4/5</td><td>A &amp; B</td></tr>
<tr><th>5</th><td>3.5/5</td><td></td></tr>
</tbody></table>
"""


FLOW = [Variant(level, f"c_30134_uni2_rsp{level}" if level else "c_30134_uni2", "Radiant Sword Flow" + (f" {numeral}" if level else ""), 1, "")
        for level, numeral in enumerate(["", "I", "II", "III", "IV", "V"])]
FLICKER = [Variant(level, f"c_30134_srt4_rsp{level}" if level else "c_30134_srt4", "Flicker Blade" + (f" ({name})" if level else ""), 0, "")
           for level, name in enumerate(["", "Amped", "Cycle", "Aegis", "Blink", "Unbound"])]


def _variants_of(card_id: str) -> list[Variant]:
    return {"c_30134_uni2": FLOW, "c_30134_srt4": FLICKER}.get(card_id, [])


# The Rossweisse "Cycle -2 | Unbound Nuke | 180 FM" deck: its cell, card, and the start of its picture's cache file name.
RW_DECK = [("B10", "c_30134_srt4", "c13817e1ee68"), *[(f"{col}10", "c_30134_uni1", "ee78230fbe93") for col in "CDEF"],
           ("B11", "c_30134_uni2", "3d35f72c9e80"), ("C11", "c_30134_uni3", "19095618d73b")]


def _rossweisse_deck() -> list[bytes] | None:
    if not (have_client_db() and have_client_text()):
        return None
    cache = client_output_dir() / ".cache" / "guides"
    found = [next(cache.glob(f"{prefix}*"), None) for _, _, prefix in RW_DECK]
    return [path.read_bytes() for path in found] if all(found) else None


def _cell(row: int, col: int, text: str = "", pictures: int = 0) -> Cell:
    return Cell(row, col, text, [f"https://example/{row}-{col}-{n}.png" for n in range(pictures)])


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _pattern(seed: int, size=(96, 96)) -> Image.Image:
    image = Image.new("RGB", size, (seed * 37 % 255, seed * 91 % 255, seed * 53 % 255))
    draw = ImageDraw.Draw(image)
    for n in range(6):
        x, y = (seed * 13 + n * 29) % size[0], (seed * 7 + n * 41) % size[1]
        draw.rectangle((x, y, x + size[0] // 3, y + size[1] // 5), fill=((n * 80 + seed * 30) % 255, (n * 50) % 255, (seed * 120) % 255))
    return image


def _textured(seed: int, size=(420, 632)) -> Image.Image:
    """Card-sized art with enough corners and blobs for SIFT to find features, the same for the same seed."""
    rng = random.Random(seed)
    image = Image.new("RGB", size, (rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    draw = ImageDraw.Draw(image)
    for _ in range(250):
        x, y, r = rng.randrange(size[0]), rng.randrange(size[1]), rng.randrange(4, 30)
        shape = draw.ellipse if rng.random() < 0.5 else draw.rectangle
        shape((x - r, y - r, x + r, y + r), fill=(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    return image.filter(ImageFilter.GaussianBlur(1))


def _framed_render(art: Image.Image) -> Image.Image:
    """`art` as the sheet shows a card: shrunk to a render with its title bar and text box painted over."""
    render = art.resize(images.CARD_RENDER_SIZE)
    draw = ImageDraw.Draw(render)
    draw.rectangle((0, 0, 132, 25), fill=(20, 20, 20))
    draw.rectangle((0, 110, 132, 197), fill=(20, 20, 20))
    return render


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Sheet


def test_tabs_unescape_names():
    assert tabs(TAB_LIST) == [("Tenebria", "484210597"), ("Adelheid/ADHD", "7")]


def test_grid_tracks_spans_line_breaks_and_images():
    grid = parse_grid(GRID)
    assert grid[(0, 0)].text == "Glossary Link"
    assert grid[(2, 0)].text == "Partners"
    assert grid[(2, 2)].images == ["https://example/face.png"]
    assert grid[(3, 0)].text == "Line one\nLine two"
    assert grid[(3, 2)].text == "A & B"
    # The rowspan above pushes row 5's first cell over to column B.
    assert grid[(4, 1)].text == "3.5/5"
    assert (1, 0) not in grid


def test_fetcher_refetches_pages_but_caches_pictures(tmp_path, monkeypatch):
    calls: list[str] = []

    def download(url: str) -> bytes:
        calls.append(url)
        return f"{url}#{len(calls)}".encode("utf-8")

    monkeypatch.setattr(Fetcher, "_download", staticmethod(download))
    fetcher = Fetcher(tmp_path)
    assert fetcher.text("page") != fetcher.text("page")
    assert fetcher.bytes("picture") == fetcher.bytes("picture")
    assert calls == ["page", "page", "picture"]


def test_column_letters():
    assert [column_letters(n) for n in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Splitting a tab


def test_bands_split_on_empty_rows_and_drop_the_glossary_link():
    grid = {(c.row, c.col): c for c in (_cell(0, 1, "Glossary Link"), _cell(2, 1, "A"), _cell(3, 1, "B"), _cell(5, 1, "C"))}
    assert [[cell.text for cell in band] for band in guides._bands(grid)] == [["A", "B"], ["C"]]


def test_panels_are_six_columns_wide_from_column_b():
    band = [_cell(0, 1, "B"), _cell(0, 6, "G"), _cell(0, 7, "H"), _cell(0, 13, "N")]
    assert [[cell.text for cell in panel] for panel in guides._panels(band)] == [["B", "G"], ["H"], ["N"]]


def test_label_rows_are_short_single_line_non_ratings():
    assert guides._is_label_row(["Cycle -11", "AP -1"])
    assert not guides._is_label_row(["4/5"])
    assert not guides._is_label_row(["a\nb"])
    assert not guides._is_label_row([])


def test_slugs_and_identifiers():
    assert naming.slug("Mei Lin") == "mei-lin"
    assert naming.slug("A" * 47 + " b", 48) == "a" * 47
    assert guides._identifier("mei-lin") == "meiLinJson"


def test_content_module_imports_every_guide_in_order():
    module = guides._content_module([("mei-lin", "Mei Lin"), ("nia", "Nia")]).decode("utf-8")
    assert "import meiLinJson from './data/mei-lin.guide.json'" in module
    assert module.index("meiLinJson as Guide") < module.index("niaJson as Guide")
    assert "export function getGuide" in module


def _prose(text: str) -> dict:
    return {"type": "prose", "body": {"en": text}}


def test_sections_drop_last_edit_and_name_parts():
    rated = {"type": "card-list", "items": [{"cardId": "c_1_uni1", "rating": "4/5", "note": {"en": ""}}]}
    teams = {"type": "team-grid", "groups": [{"members": [{"charResId": 1003, "name": "Mika"}]}]}
    sections, updated = guides._tidy_sections([
        {"title": None, "blocks": [rated]},
        {"title": None, "blocks": [_prose("Last Edit"), _prose("10/24")]},
        {"title": None, "blocks": [teams]},
        {"title": "Notes", "blocks": [_prose("A")]},
        {"title": None, "blocks": [_prose("B")]},
    ])
    assert updated == "10/24"
    assert [section["title"]["en"] for section in sections] == ["Card ratings", "Teams", "Notes", "Notes"]


def test_set_named_section_title_leads_with_a_set_list():
    sections, _ = guides._tidy_sections([{"title": "Radiance | Executioners", "blocks": [_prose("BlackWing | Executioners | Flex"), _prose("Crit")]}])
    blocks = sections[0]["blocks"]
    assert [block["type"] for block in blocks] == ["set-list", "set-list", "prose"]
    assert [item.get("setId") for item in blocks[0]["items"]] == [30, 11]


def _section(title: str, *types: str) -> dict:
    return {"title": {"en": title}, "blocks": [{"type": block_type} for block_type in types]}


# The Rossweisse tab, band by band.
ROSSWEISSE = [_section("Rossweisse's Self Buffs", "deck", "prose"), _section("Cycle -2 | Unbound Nuke | 180 FM", "deck", "rating-list"),
              _section("Sig | Scarlet | Westmacott", "partner-list"), _section("Radiance | Executioners", "set-list", "prose"),
              _section("Potentials & Ego", "potentials"), _section("Card ratings", "card-list", "prose"), _section("Rossweisse Example Teams", "team-grid")]


def _headings(page: dict) -> list[str]:
    return [block["text"]["en"] for block in page["blocks"] if block["type"] == "heading"]


def test_rossweisse_fills_the_seven_pages_in_order():
    pages = guides._pages(ROSSWEISSE, {})
    assert [page["id"] for page in pages] == ["playstyle", "decks", "partners", "relics", "potentials", "card-ratings", "teams"]
    assert not any(page.get("missing") for page in pages)
    by_id = {page["id"]: page for page in pages}
    assert _headings(by_id["playstyle"]) == ["Rossweisse's Self Buffs"]
    assert _headings(by_id["decks"]) == ["Cycle -2 | Unbound Nuke | 180 FM"]
    # These band titles only repeat the page, or are already shown as set cards.
    assert not any(_headings(by_id[page_id]) for page_id in ("partners", "relics", "potentials", "card-ratings", "teams"))


def test_extras_after_the_partners_go_to_seasons_and_chaos():
    sections = [_section("Nia's card draw", "prose"), _section("Season 4 Exclusive", "prose"), _section("Standard Hunt Base", "deck"),
                *ROSSWEISSE[1:5], _section("Season 4 | Shattered Light and Claw", "card-list"), _section("Desire Synergy:", "prose"),
                _section("Notes", "prose"), _section("C7 Burning Life", "prose"), *ROSSWEISSE[5:]]
    pages = {page["id"]: page for page in guides._pages(sections, {})}
    assert _headings(pages["playstyle"]) == ["Nia's card draw", "Season 4 Exclusive"]
    assert _headings(pages["decks"]) == ["Standard Hunt Base", "Cycle -2 | Unbound Nuke | 180 FM"]
    assert list(pages)[-1] == "seasons-chaos"
    assert pages["seasons-chaos"]["title"] == {"en": "Seasons & Chaos"}
    assert _headings(pages["seasons-chaos"]) == ["Season 4 | Shattered Light and Claw", "Desire Synergy:", "Notes", "C7 Burning Life"]


def test_a_page_the_sheet_lacks_is_marked_missing():
    pages = {page["id"]: page for page in guides._pages([section for section in ROSSWEISSE if section["title"]["en"] != "Potentials & Ego"], {})}
    assert pages["potentials"] == {"id": "potentials", "title": {"en": "Potentials & Ego"}, "blocks": [], "missing": True}
    assert "seasons-chaos" not in pages


def test_a_band_can_be_moved_to_another_page():
    pages = {page["id"]: page for page in guides._pages(ROSSWEISSE, {"Cycle -2 | Unbound Nuke | 180 FM": "playstyle"})}
    assert pages["decks"]["missing"] and len(_headings(pages["playstyle"])) == 2


def _rated(card_id: str, name: str, rating: str, level: int | None = None) -> dict:
    item = {"cardId": card_id, "name": name, "cost": 1, "rating": rating, "note": {"en": ""}}
    return item if level is None else {**item, "level": level}


def test_fold_makes_one_item_per_epiphany_set():
    ratings = ["1/5", "5/5", "1/5", "3/5", "5/5"]
    [item] = guides._fold([_rated("c_30134_uni2", "Radiant Sword Flow", rating, level) for level, rating in enumerate(ratings, 1)], _variants_of)
    assert "cost" not in item and "rating" not in item
    assert [(ep["level"], ep["rating"]) for ep in item["epiphanies"]] == list(enumerate(ratings, 1))
    assert item["epiphanies"][1] == {"level": 2, "name": "Radiant Sword Flow II", "cost": 1, "rating": "5/5", "note": {"en": ""}}


def test_fold_leaves_cards_without_variants_alone():
    tassel = _rated("c_30134_cre1", "Sword Tassel", "5/5")
    assert guides._fold([tassel, _rated("c_30134_cre1", "Sword Tassel", "4/5", 2)], _variants_of) == [tassel, {**tassel, "rating": "4/5"}]


def test_only_a_complete_rated_run_gets_levels():
    # An unidentified picture or another card in the middle restarts the count, and a short run misses levels.
    runs = [("c_30134_uni2", position) for position in range(1, 6)] + [("c_30134_srt4", position) for position in (1, 1, 2, 3, 4)]
    cards = [{"cardId": card_id, "epiphany": position} for card_id, position in runs + [("c_30134_cre1", 1), ("c_30134_cre1", 2)]]
    assert guides._complete_runs(cards, _variants_of) == {"c_30134_uni2"}
    assert guides._complete_runs([{"cardId": "c_30134_uni2", "epiphany": position} for position in (1, 2, 3)], _variants_of) == set()


def test_notes_attach_by_name_number_and_game_name():
    cards = {"type": "card-list", "items": guides._fold(
        [_rated("c_30134_uni2", "Radiant Sword Flow", "5/5", level) for level in range(1, 6)]
        + [_rated("c_30134_srt4", "Flicker Blade", "5/5", level) for level in range(1, 6)]
        + [_rated("c_30134_cre1", "Sword Tassel", "5/5")], _variants_of)}
    partners = {"type": "partner-list", "items": [{"charResId": 30135, "name": "Sig", "rating": "6/5", "note": {"en": ""}}]}
    blocks = guides._attach_notes([cards, _prose("Flow 2: Its great\nUnbound: Ap and 1 Cost\nTassel: BASE DAMAGE"), partners, _prose("Sig: busted")])
    assert [block["type"] for block in blocks] == ["card-list", "partner-list"]
    flow, flicker, tassel = cards["items"]
    assert flow["epiphanies"][1]["note"] == {"en": "Its great"}
    assert flicker["epiphanies"][4]["note"] == {"en": "Ap and 1 Cost"}
    assert tassel["note"] == {"en": "BASE DAMAGE"}
    assert partners["items"][0]["note"] == {"en": "busted"}


def test_unmatched_note_lines_stay_in_prose():
    cards = {"type": "card-list", "items": [_rated("c_30134_cre1", "Sword Tassel", "5/5")]}
    blocks = guides._attach_notes([cards, _prose("Equilux: Start of turn\nTassel: base\nPlain line")])
    assert blocks[1] == _prose("Equilux: Start of turn\nPlain line")


def _builder(entries: dict | None = None, picture_size=(1200, 140)) -> guides._GuideBuilder:
    # Every picture is the same banner, so nothing needs a matcher.
    banner = guides._Download(_png(_pattern(5, picture_size)))
    ctx = SimpleNamespace(text=lambda text, **_: text)
    downloads = SimpleNamespace(get=lambda url: banner)
    return guides._GuideBuilder(ctx, downloads, None, None, None, None, {}, _variants_of, guides._DeckPictures(), SimpleNamespace(entries=entries or {}),
                                guides._PictureLabels({}), "Tab", "tab")


def _grid(*cells: Cell) -> dict[tuple[int, int], Cell]:
    return {(cell.row, cell.col): cell for cell in cells}


def test_text_beside_a_picture_is_kept():
    sections, _ = _builder().sections(_grid(_cell(20, 1, pictures=1), _cell(20, 4, "Important Substats:\nCrt Rate/Crt Dmg")))
    assert sections[0]["blocks"] == [_prose("Important Substats:\nCrt Rate/Crt Dmg")]


def test_text_beside_faces_is_left_out():
    # Template filler such as "DPS" sits beside the example team faces.
    sections, _ = _builder({"Tab!D66": {"charResId": 1003}}).sections(_grid(_cell(65, 2, "DPS"), _cell(65, 3, pictures=1)))
    assert [block["type"] for block in sections[0]["blocks"]] == ["team-grid"]


LEGEND = "Purple: Main Damage Boosts\n\nGold: QOL\n\nBlue: Irrelevant usually"
EGO = "E1: \nPretty good\n\nE2:\nAbsolutely broken\n\nE3: Fine\nE4\nOkay\nE3: \nTypo for E5\nE6:\nE2's damage gets better"


def _potentials_grid(tree: bool = True, legend: str = LEGEND) -> dict[tuple[int, int], Cell]:
    # The Rossweisse layout: headings on row 24, the tree in B25, the legend in E25 and the ego notes in H25.
    cells = [_cell(23, 2, "Potentials"), _cell(23, 8, "Ego Manifestation"), _cell(24, 4, legend), _cell(24, 7, EGO)]
    return _grid(*cells, *([_cell(24, 1, pictures=1)] if tree else []))


def test_potentials_band_becomes_one_block():
    builder = _builder(picture_size=(371, 318))
    sections, _ = builder.sections(_potentials_grid())
    [section] = sections
    assert section["title"] == {"en": "Potentials & Ego"}
    [block] = section["blocks"]
    assert block["image"] == "tab.webp" and set(builder.pictures) == {"tab.webp"}
    assert block["legend"] == [{"colour": "purple", "text": {"en": "Main Damage Boosts"}}, {"colour": "gold", "text": {"en": "QOL"}},
                               {"colour": "blue", "text": {"en": "Irrelevant usually"}}]
    # Levels follow the order the notes are written in, as some tabs label E5 as "E3".
    assert block["ego"] == [{"level": level, "text": {"en": text}} for level, text in
                            enumerate(["Pretty good", "Absolutely broken", "Fine", "Okay", "Typo for E5", "E2's damage gets better"], 1)]


def test_a_tiny_tree_picture_still_counts():
    builder = _builder(picture_size=(23, 20))
    [section], _ = builder.sections(_potentials_grid())
    assert section["blocks"][0]["image"] == "tab.webp"


def test_potentials_without_a_tree_picture():
    builder = _builder()
    [section], _ = builder.sections(_potentials_grid(tree=False))
    assert section["blocks"][0]["image"] is None and not builder.pictures


def test_potentials_legend_keeps_other_wording_and_extra_lines():
    legend = "Purple: Main Identity Boost\nGold: QOL\nBlue: Irrelevant usually\nNothing is THAT important"
    [section], _ = _builder().sections(_potentials_grid(legend=legend))
    potentials, extra = section["blocks"]
    assert potentials["legend"][0] == {"colour": "purple", "text": {"en": "Main Identity Boost"}}
    assert extra == _prose("Nothing is THAT important")


def test_purple_without_a_colon_is_not_a_legend():
    sections, _ = _builder().sections(_grid(_cell(64, 7, "Red DPS\nteam"), _cell(64, 8, "Purple DPS\nteam")))
    assert all(block["type"] == "prose" for block in sections[0]["blocks"])


def _download(seed: int) -> guides._Download:
    return guides._Download(_png(_textured(seed)))


def _never(data: bytes) -> str:
    raise AssertionError("a card known some other way should not be read")


def test_deck_card_takes_an_exact_copy_first():
    picture = _download(1)
    library = guides._DeckPictures()
    library.add_copy("c_30134_uni2", picture, 3)
    card = {"cardId": "c_30134_uni2", "name": "Radiant Sword Flow", "cost": 1}
    assert guides._resolve_deck_card(card, picture, "Tab!B10", library, {}, _never, _variants_of)
    assert card["epiphany"] == {"level": 3, "name": "Radiant Sword Flow III", "text": {"en": ""}}
    assert "extra" not in card


def test_deck_card_override_wins():
    picture = _download(2)
    library = guides._DeckPictures()
    library.add_copy("c_30134_uni2", picture, 3)
    card = {"cardId": "c_30134_uni2", "cost": 1}
    overrides = {"Tab!C10": {"epiphany": 2, "divine": "div_0098", "_why": "test"}}
    assert guides._resolve_deck_card(card, picture, "Tab!C10", library, overrides, _never, _variants_of)
    assert card["epiphany"]["level"] == 2
    assert card["extra"] == {"id": "div_0098", "god": "Nihilum", "text": {"en": "Reduce Cost of this card by 1."}}
    assert card["cost"] == 0


def test_unresolved_deck_card_is_listed_for_review():
    picture = _download(3)
    card = {"cardId": "c_30134_uni2", "cost": 1}
    assert not guides._resolve_deck_card(card, picture, "Tab!D10", guides._DeckPictures(), {}, lambda data: "zzzz", _variants_of)
    assert "epiphany" not in card
    unknown: dict[str, guides._Picture] = {}
    guides._add_unknown_epiphany(unknown, picture, "Tab!D10")
    page = guides._review_page({}, unknown).decode("utf-8")
    assert "Deck cards with an unknown epiphany" in page and "Tab!D10" in page and "cell override" in page


def test_unknown_deck_pictures_are_listed_by_exact_file():
    # Two levels of one card hash almost alike, so only an identical file is the same entry.
    image = _textured(5)
    other = image.copy()
    other.putpixel((0, 0), (255, 0, 0))
    first, second = guides._Download(_png(image)), guides._Download(_png(other))
    assert (first.hash ^ second.hash).bit_count() <= guides.PICTURE_LABEL_DISTANCE
    unknown: dict[str, guides._Picture] = {}
    for download, ref in ((first, "Tab!B10"), (second, "Tab!C10"), (first, "Tab!D10")):
        guides._add_unknown_epiphany(unknown, download, ref)
    assert [picture.refs for picture in unknown.values()] == [["Tab!B10", "Tab!D10"], ["Tab!C10"]]


def test_deck_copies_of_one_picture_are_matched_once():
    picture = _download(4)
    library = guides._DeckPictures()
    reads = []
    for cell in ("D10", "E10"):
        card = {"cardId": "c_30134_uni2", "cost": 1}
        assert not guides._resolve_deck_card(card, picture, f"Tab!{cell}", library, {}, lambda data: reads.append(data) or "zzzz", _variants_of)
    assert len(reads) == 1


def test_unrated_card_row_becomes_a_deck_with_every_copy():
    resonance = {"cardId": "c_30134_uni1", "name": "Sword Resonance", "cost": 1, "note": {"en": ""}}
    deck = guides._as_deck({"type": "card-list", "items": [dict(resonance) for _ in range(4)]})
    assert deck == {"type": "deck", "cards": [{"cardId": "c_30134_uni1", "name": "Sword Resonance", "cost": 1}] * 4}
    assert guides._as_deck({"type": "card-list", "items": [{**resonance, "rating": "4/5"}]}) is None


def test_rossweisse_deck_epiphanies():
    pytest.importorskip("rapidocr_onnxruntime")
    pictures = _rossweisse_deck()
    if pictures is None:
        pytest.skip("the Rossweisse deck pictures or the game client DB are not available")
    ctx = Context(client_output_dir())
    text_cache: dict[str, str] = {}
    cards = []
    for (cell, card_id, _), data in zip(RW_DECK, pictures):
        card = {"cardId": card_id, "cost": epiphany.printed_cost(ctx, card_id)}
        read = lambda data: card_text.read_card_text(data, text_cache)
        assert guides._resolve_deck_card(card, guides._Download(data), f"Rossweisse!{cell}", guides._DeckPictures(), {}, read,
                                         lambda card_id: epiphany.variants(ctx, card_id))
        cards.append(card)
    assert [card["epiphany"]["level"] for card in cards] == [5, 2, 2, 2, 2, 5, 0]
    assert all(card["extra"]["id"] == "div_0098" and card["cost"] == 0 for card in cards[1:5])


def test_find_set_reads_sheet_shorthand():
    assert [set_names.find_set(label) for label in ("BlackWing", "Executioners", "BattleField Evo", "Scrab", "Radiance")] == [9, 11, 28, 10, 30]


def test_find_set_refuses_ambiguous_and_unknown():
    assert set_names.find_set("Flex") is None
    assert set_names.find_set("") is None
    assert set_names.find_set("Black Order") is None
    # "Blink" is one letter off "Black", but "Flow" fits no word of Black Wing, so a deck heading is not a set.
    assert set_names.set_line("Cycle -2 | Blink Flow | 180 FM") is None


def test_set_line_needs_a_set_and_pipes():
    items = set_names.set_line("BlackWing | Executioners | Flex")
    assert items[0] == {"label": "BlackWing", "setId": 9, "name": "Black Wing", "pieces": 2, "bonus": "+12% Attack", "icon": "/assets/pieces/icon_piece_set_009.png"}
    assert items[2] == {"label": "Flex"}
    assert set_names.set_line("A | B") is None
    assert set_names.set_line("BlackWing") is None
    assert "icon" not in set_names.set_line("Wireth's Steel | Flex")[0]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Pictures


def test_picture_kinds_from_shape():
    assert images.kind(Image.new("RGB", (96, 96))) == "face"
    assert images.kind(Image.new("RGB", (133, 198))) == "card"
    assert images.kind(Image.new("RGB", (1200, 140))) == "other"


def test_picture_labels_match_near_copies_and_merge_unidentified():
    picture = _pattern(3)
    labels = guides._PictureLabels({f"{images.dhash(picture):064x}": {"charResId": 1003}})
    assert labels.find(images.dhash(picture.resize((90, 90)).resize((96, 96)))) == {"charResId": 1003}
    assert labels.find(images.dhash(_pattern(9))) == {}
    labels.unidentify(images.dhash(_pattern(9)), b"x", "face", "Tab!B3")
    labels.unidentify(images.dhash(_pattern(9).resize((95, 95))), b"x", "face", "Tab!C3")
    [entry] = labels.unidentified.values()
    assert entry.refs == ["Tab!B3", "Tab!C3"]


def test_review_page_lists_the_hash_and_uses():
    labels = guides._PictureLabels({})
    labels.unidentify(images.dhash(_pattern(4)), _png(_pattern(4)), "card", "Tab!D5")
    page = guides._review_page(labels.unidentified).decode("utf-8")
    assert "data:image/png;base64," in page and "Tab!D5" in page and "1 unidentified" in page


def test_face_matcher_finds_the_exact_portrait(tmp_path):
    for res_id, seed in ((1003, 1), (1004, 2), (1005, 3)):
        _pattern(seed).save(tmp_path / f"shortcut_face_character_{res_id}.png")
    matcher = images.FaceMatcher(tmp_path)
    assert matcher.match(_pattern(2)) == 1004
    assert matcher.match(Image.new("RGB", (96, 96), (5, 5, 5))) is None


def test_card_matcher_finds_the_art_under_a_frame(tmp_path):
    arts = {name: _pattern(seed, (420, 632)) for name, seed in (("unique_1_01", 11), ("unique_1_02", 12), ("unique_1_03", 13))}
    for name, art in arts.items():
        art.save(tmp_path / f"{name}.png")
    matcher = images.CardMatcher({name: tmp_path / f"{name}.png" for name in arts})
    assert matcher.match(_framed_render(arts["unique_1_02"])) == "unique_1_02"


def test_sift_matcher_finds_another_characters_card_under_a_frame(tmp_path):
    pytest.importorskip("cv2")
    for seed in (21, 22, 23):
        _textured(seed).save(tmp_path / f"c_{seed}.png")
    matcher = images.SiftMatcher({f"c_{seed}": [tmp_path / f"c_{seed}.png"] for seed in (21, 22, 23)},
                                 query_size=images.CARD_RENDER_SIZE, query_box=images.CARD_ART_WINDOW)
    assert matcher.match(_framed_render(_textured(22))) == "c_22"
    assert matcher.match(_framed_render(_textured(99))) is None


def test_sift_matcher_tells_recoloured_art_apart_by_colour(tmp_path):
    pytest.importorskip("cv2")
    # The same art tinted red and blue at equal brightness, as with a monster card and its stronger form. SIFT sees them as one.
    art = _textured(32).convert("L").point(lambda value: 40 + value * 175 // 255)
    red, blue = (Image.merge("RGB", [art.point(lambda value, shift=shift: value + shift) for shift in tint]) for tint in ((40, -20, 0), (-40, 20, 0)))
    red.save(tmp_path / "m_0001.png")
    blue.save(tmp_path / "m_0002.png")
    matcher = images.SiftMatcher({"m_0001": [tmp_path / "m_0001.png"], "m_0002": [tmp_path / "m_0002.png"]},
                                 query_size=images.CARD_RENDER_SIZE, query_box=images.CARD_ART_WINDOW)
    assert matcher.match(_framed_render(blue)) == "m_0002"
    assert matcher.match(_framed_render(red)) == "m_0001"


def test_card_art_lists_a_shared_image_once_under_its_plainest_id(tmp_path, monkeypatch):
    folder = tmp_path / "combatants" / "rin"
    folder.mkdir(parents=True)
    for stem, seed in (("c_1018_srt4_rsp1", 1), ("c_1018_srt4", 1), ("c_1018_uni1", 2)):
        _pattern(seed).save(folder / f"{stem}.webp")
    monkeypatch.setattr(guides, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guides, "CARD_ART_DIRS", (folder.relative_to(tmp_path),))
    assert sorted(guides._card_art()) == ["c_1018_srt4", "c_1018_uni1"]


def test_cached_sift_remembers_results_without_building_the_matcher(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the matcher should not be built on a cache hit")

    monkeypatch.setattr(images, "SiftMatcher", fail)
    cache: dict[str, str] = {}
    cached = guides._CachedSift("sift-cards", {"n_0001": []}, cache)
    data = b"picture"
    cache[f"{guides.hashlib.sha1(data).hexdigest()}:sift-cards:{cached.signature}"] = "n_0001"
    assert cached.match(Image.new("RGB", (133, 198)), data) == "n_0001"
