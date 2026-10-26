"""
Tests for the Guides import: the sheet's HTML grid, splitting a tab into sections, picture labels and the image matchers.
Everything runs on synthetic inputs, so no network or extracted client is needed.
"""

from __future__ import annotations

import hashlib
import io
import os
import random
import urllib.error
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFilter

from api.client_db import client_output_dir, have_client_db, have_client_text
from scripts.datagen import card_text, epiphany, guides_qc, images, naming, set_names, sheet
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


# The Rossweisse "Cycle -2 | Unbound Nuke | 180 FM" deck: its cell, card, and the start of its picture's sha1.
RW_DECK = [("B10", "c_30134_srt4", "f8ae3a4126e2"), *[(f"{col}10", "c_30134_uni1", "c92c557f20ef") for col in "CDEF"],
           ("B11", "c_30134_uni2", "f25269e88665"), ("C11", "c_30134_uni3", "dfd4da2efaee")]


# A neutral card as the deck builder's shared pool lists it.
SPORE_HARVESTER = {"id": "n_0129", "name": "Spore Harvester", "cost": 0,
                   "description": "[Retain] [Exhaust] Incinerate: Create 2 Contaminated Spore. Retain: Create 1 Contaminated Spore."}


def _rossweisse_deck() -> list[bytes] | None:
    if not (have_client_db() and have_client_text()):
        return None
    # Found by content, as the cache names a picture by its tab's layout, which changes whenever the sheet is edited.
    cache = client_output_dir() / ".cache" / "guides" / "pictures"
    by_sha1 = {hashlib.sha1(data).hexdigest()[:12]: data for data in (path.read_bytes() for path in cache.glob("*"))}
    found = [by_sha1.get(prefix) for _, _, prefix in RW_DECK]
    return found if all(found) else None


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


def test_grid_marks_the_bold_characters_of_a_cell():
    page = '<table><tbody><tr><th>1</th><td> <span style="font-weight:bold;">Bold</span> plain<br><span style="color:red">red</span></td></tr></tbody></table>'
    cell = parse_grid(page)[(0, 0)]
    assert cell.text == "Bold plain\nred"
    assert cell.bold == [(0, 4)]


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


def _counting_fetcher(tmp_path, monkeypatch) -> tuple[Fetcher, list[str]]:
    """
    A fetcher whose downloads are recorded instead of sent.

    Args:
        tmp_path: The cache folder.
        monkeypatch: Replaces the network call.

    Returns:
        The fetcher and the list of URLs it downloads.
    """
    calls: list[str] = []
    monkeypatch.setattr(Fetcher, "_download", staticmethod(lambda url: calls.append(url) or url.encode("utf-8")))
    return Fetcher(tmp_path), calls


def test_fetcher_refetches_pages_but_caches_pictures(tmp_path, monkeypatch):
    fetcher, calls = _counting_fetcher(tmp_path, monkeypatch)
    fetcher.text("page")
    fetcher.text("page")
    assert fetcher.bytes("picture", "Olga!B3#0") == fetcher.bytes("picture", "Olga!B3#0")
    assert calls == ["page", "page", "picture"]


def test_fetcher_keeps_a_picture_whose_address_changed(tmp_path, monkeypatch):
    # Google hands out a new address for every picture on later runs, so the key is what names it.
    fetcher, calls = _counting_fetcher(tmp_path, monkeypatch)
    assert fetcher.bytes("address-1", "Olga!B3#0") == fetcher.bytes("address-2", "Olga!B3#0") == b"address-1"
    assert calls == ["address-1"]


def test_fetcher_refetches_an_old_picture(tmp_path, monkeypatch):
    fetcher, calls = _counting_fetcher(tmp_path, monkeypatch)
    fetcher.bytes("address-1", "Olga!B3#0")
    (path,) = tmp_path.iterdir()
    os.utime(path, (0, 0))
    assert fetcher.bytes("address-2", "Olga!B3#0") == b"address-2"
    assert calls == ["address-1", "address-2"]


def test_fetcher_prunes_the_pictures_a_run_did_not_use(tmp_path, monkeypatch):
    fetcher, _ = _counting_fetcher(tmp_path, monkeypatch)
    fetcher.bytes("address-1", "Olga!B3#0")
    fetcher.bytes("address-2", "Olga!B4#0")
    fetcher, _ = _counting_fetcher(tmp_path, monkeypatch)
    assert fetcher.bytes("address-3", "Olga!B3#0") == b"address-1"
    fetcher.prune()
    assert len(list(tmp_path.iterdir())) == 1


def test_downloads_cache_a_shared_address_under_every_cell(tmp_path, monkeypatch):
    # Two cells share an address on some runs and not on others, so the second cell needs its own copy for the next run.
    fetcher, calls = _counting_fetcher(tmp_path, monkeypatch)
    monkeypatch.setattr(guides, "_Download", lambda data: SimpleNamespace(data=data))
    downloads = guides._Downloads(fetcher)
    downloads.get("address-1", "Olga!C10#0")
    downloads.get("address-1", "Olga!D10#0")
    fetcher.prune()
    fetcher, calls = _counting_fetcher(tmp_path, monkeypatch)
    assert fetcher.bytes("address-2", "Olga!D10#0") == b"address-1"
    assert calls == []


def test_layout_ignores_picture_addresses_but_not_moved_pictures():
    def grid(*rows: tuple[str, str]) -> dict[tuple[int, int], Cell]:
        return {(row, 0): Cell(row, 0, text, [url] if url else []) for row, (text, url) in enumerate(rows)}

    before = sheet.layout(grid(("Deck", ""), ("", "https://x/AAAA=w133-h199")))
    assert sheet.layout(grid(("Deck", ""), ("", "https://x/BBBB=w133-h199"))) == before
    # An inserted row moves the picture down, so the picture now at B2 may be a different one.
    assert sheet.layout(grid(("Deck", ""), ("New note", ""), ("", "https://x/BBBB=w133-h199"))) != before
    assert sheet.layout(grid(("Deck", ""), ("", "https://x/BBBB=w371-h20"))) != before


def test_fetcher_retries_a_failed_download(monkeypatch):
    attempts: list[str] = []

    class Response(io.BytesIO):
        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        attempts.append(request.full_url)
        if len(attempts) < 3:
            raise urllib.error.URLError("The handshake operation timed out")
        return Response(b"picture")

    monkeypatch.setattr(sheet.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sheet.time, "sleep", lambda seconds: None)
    assert Fetcher._download("https://example.com/a.png") == b"picture"
    assert len(attempts) == 3


def test_fetcher_gives_up_after_its_attempts(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(sheet.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sheet.time, "sleep", lambda seconds: None)
    with pytest.raises(urllib.error.URLError):
        Fetcher._download("https://example.com/a.png")


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


def _flow_list() -> dict:
    return {"type": "card-list", "items": guides._fold([_rated("c_30134_uni2", "Radiant Sword Flow", "5/5", level) for level in range(1, 6)], _variants_of)}


def test_notes_accept_initials_commas_quotes_and_typos():
    cards = _flow_list()
    blocks = guides._attach_notes([cards, _prose('RSF 1, 1 cost is bad\nRSF 2: Very good\nFlow 3" Zero cost\nFlowe 4, Typo')])
    assert len(blocks) == 1
    assert [level["note"]["en"] for level in cards["items"][0]["epiphanies"]] == ["1 cost is bad", "Very good", "Zero cost", "Typo", ""]


def test_a_single_ladder_takes_numbered_lines_by_position():
    cards = _flow_list()
    blocks = guides._attach_notes([cards, _prose("Zap 1: one\nZap 2: two\nNot numbered")])
    assert [level["note"]["en"] for level in cards["items"][0]["epiphanies"]][:3] == ["one", "two", ""]
    assert blocks[1] == _prose("Not numbered")


def test_one_odd_numbered_line_is_not_taken_by_position():
    cards = _flow_list()
    blocks = guides._attach_notes([cards, _prose("Costs 2, usually")])
    assert len(blocks) == 2


def test_unmatched_note_lines_stay_in_prose():
    cards = {"type": "card-list", "items": [_rated("c_30134_cre1", "Sword Tassel", "5/5")]}
    blocks = guides._attach_notes([cards, _prose("Equilux: Start of turn\nTassel: base\nPlain line")])
    assert blocks[1] == _prose("Equilux: Start of turn\nPlain line")


def _builder(entries: dict | None = None, picture_size=(1200, 140)) -> guides._GuideBuilder:
    # Every picture is the same banner, so nothing needs a matcher.
    banner = guides._Download(_png(_pattern(5, picture_size)))
    ctx = SimpleNamespace(text=lambda text, **_: text)
    downloads = SimpleNamespace(get=lambda url, key: banner)
    return guides._GuideBuilder(ctx, downloads, None, None, None, None, {}, {}, _variants_of, guides._DeckPictures(), SimpleNamespace(entries=entries or {}),
                                guides._PictureLabels({}), "Tab", "tab", None, None, lambda data: "")


def _grid(*cells: Cell) -> dict[tuple[int, int], Cell]:
    return {(cell.row, cell.col): cell for cell in cells}


def test_text_beside_a_picture_is_kept():
    sections, _ = _builder(picture_size=(120, 100)).sections(_grid(_cell(20, 1, pictures=1), _cell(20, 4, "Important Substats:\nCrt Rate/Crt Dmg")))
    assert sections[0]["blocks"] == [_prose("Important Substats:\nCrt Rate/Crt Dmg")]


def test_small_unmatched_icon_is_dropped_without_review():
    builder = _builder(picture_size=(123, 120))
    sections, _ = builder.sections(_grid(_cell(20, 1, pictures=1)))
    assert not sections and not builder.labels.unidentified and not builder.strips


def test_wide_unmatched_strip_becomes_an_image_block():
    builder = _builder(picture_size=(1200, 140))
    sections, _ = builder.sections(_grid(_cell(20, 1, pictures=1), _cell(20, 4, "Important Substats")))
    [image, text] = sections[0]["blocks"]
    assert image["type"] == "image" and image["image"] in builder.strips and image["image"].endswith(".webp")
    assert text == _prose("Important Substats") and not builder.labels.unidentified


def test_large_narrow_unmatched_picture_still_needs_review():
    builder = _builder(picture_size=(300, 200))
    sections, _ = builder.sections(_grid(_cell(20, 1, pictures=1)))
    assert not sections and len(builder.labels.unidentified) == 1


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


def test_mostly_bold_ego_levels_are_marked_bold():
    # E1 is all bold, E2 is half bold, E3 is plain, and the "E1:" headings themselves do not count.
    pieces = [("E1:\n", False), ("Big deal", True), ("\nE2:\n", False), ("Half", True), (" and half", False), ("\nE3:\nPlain", False)]
    text = "".join(piece for piece, _ in pieces)
    bold, at = [], 0
    for piece, flag in pieces:
        if flag:
            bold.append((at, at + len(piece)))
        at += len(piece)
    cells = [_cell(23, 2, "Potentials"), _cell(24, 4, LEGEND), Cell(24, 7, text, bold=bold)]
    [section], _ = _builder().sections(_grid(*cells))
    assert [(note["level"], note.get("bold")) for note in section["blocks"][0]["ego"]] == [(1, True), (2, None), (3, None)]


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


def test_deck_card_with_no_epiphanies_shows_its_own_text(monkeypatch):
    builder = _builder()
    builder.ctx = SimpleNamespace(client=SimpleNamespace(cards={"c_1040_uni4": {}, "c_30134_uni2": {}}))
    builder.shared_cards = {"n_0129": SPORE_HARVESTER}
    monkeypatch.setattr(guides.epiphany, "base_text", lambda ctx, card_id: "Create 1 Opening Found.")
    specialist = {"cardId": "c_1040_uni4", "name": "Heavy Weapons Specialist", "cost": 1, "note": {"en": ""}}
    flow = {"cardId": "c_30134_uni2", "name": "Radiant Sword Flow", "cost": 1, "note": {"en": ""}}
    neutral = {"cardId": "n_0129", "name": "Spore Harvester", "note": {"en": ""}}
    unknown = {"cardId": "n_9999", "name": "Unknown", "note": {"en": ""}}
    deck = builder._deck_or_list({"type": "card-list", "items": [specialist, flow, neutral, unknown]})
    assert deck["cards"][0]["text"] == {"en": "Create 1 Opening Found."}
    # A card with epiphanies gets its text from the one it shows, and a card no data knows gets none.
    assert "text" not in deck["cards"][1] and "text" not in deck["cards"][3]
    # A neutral or monster card takes its text from the deck builder's shared pool.
    assert deck["cards"][2]["text"] == {"en": SPORE_HARVESTER["description"]}


def test_neutral_card_takes_its_cost_from_the_shared_pool():
    builder = _builder()
    builder.ctx = SimpleNamespace(client=SimpleNamespace(cards={}))
    builder.card_names = {"n_0129": "Spore Harvester"}
    builder.shared_cards = {"n_0129": SPORE_HARVESTER}
    block = builder._card_list([{"cardId": "n_0129", "col": 1, "picture": None, "epiphany": 0}], {})
    assert block["items"][0]["cost"] == 0


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


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# QC report


def _qc_guide(blocks: list[dict]) -> list[tuple[str, str, dict]]:
    return [("olga", "Olga", {"sections": [{"id": "card-ratings", "blocks": blocks}]})]


def _qc_item(card_id: str, name: str, **extra) -> dict:
    return {"cardId": card_id, "name": name, "note": {"en": ""}, **extra}


def test_qc_counts_each_problem_class():
    ladder = {"level": 1, "name": "x", "cost": 1, "note": {"en": ""}}
    blocks = [
        {"type": "card-list", "items": [_qc_item("c_1_a", "A", rating="4/5"), _qc_item("c_1_a", "A", rating="3/5"),
                                        _qc_item("c_1_b", "B", epiphanies=[ladder, {**ladder, "level": 2}])]},
        {"type": "prose", "body": {"en": 'Flow 2: nice\nTruth 3" nice\nJust prose'}},
    ]
    found = guides_qc.collect(_qc_guide(blocks), lambda card_id: [None] * 6, {"Olga": ["Olga!B3"]}, {"dropped_icons": ["Olga!C4"]})
    assert [len(found[key]) for key in guides_qc.CLASSES] == [1, 1, 2, 1, 1]
    assert guides_qc.summary(found) == ("guides QC: unfolded_duplicates=1 empty_ladders=1 loose_numbered_lines=2 unidentified_rated=1 short_ladders=1 "
                                        "dropped_icons=1 positional_notes=0 filled_pictures=0")
    assert b"Olga!C4" in guides_qc.report(found)
    assert b"c_1_a x2" in guides_qc.report(found)


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Unread pictures and repeated cards


def _row(*card_ids: str | None) -> list[dict]:
    return [{"cardId": card_id, "col": col, "picture": None} for col, card_id in enumerate(card_ids)]


def test_title_cards_match_a_read_title_to_a_card_name():
    cache = {hashlib.sha1(data).hexdigest(): title for data, title in [(b"a", "Flicker Bladc"), (b"b", "Guard"), (b"c", "Strike"), (b"d", "Zzzzzzzz")]}
    names = {"c_1_srt4": "Flicker Blade", "c_1_srt4_rsp1": "Flicker Blade (Amped)", "c_1_def1": "Guard", "c_2_str1": "Strike", "c_3_str1": "Strike"}
    titles = guides._TitleCards(names, cache)
    assert titles.card_id(b"a", set()) == "c_1_srt4"
    assert titles.card_id(b"a", set(), 0.99) is None
    assert titles.card_id(b"b", set()) == "c_1_def1"
    # A name shared by two characters' cards is the guide character's, and nothing without an owner.
    assert titles.card_id(b"c", {"c_3_str1"}) == "c_3_str1"
    assert titles.card_id(b"c", set()) is None
    assert titles.card_id(b"d", set()) is None


def test_an_unread_picture_takes_the_card_that_completes_its_run():
    flow = "c_30134_uni2"
    row = _row(None, flow, flow, flow, flow)
    guides._fill_unread(row, _variants_of)
    assert [card["cardId"] for card in row] == [flow] * 5
    middle = _row(flow, flow, None, flow, flow)
    guides._fill_unread(middle, _variants_of)
    assert [card["epiphany"] for card in guides._number_runs(middle)] == [1, 2, 3, 4, 5]


def test_an_unread_picture_that_does_not_complete_a_run_stays_a_gap():
    row = _row("c_30134_uni2", "c_30134_uni2", None)
    guides._fill_unread(row, _variants_of)
    assert row[2]["cardId"] is None
    assert [card["epiphany"] for card in guides._number_runs(row)] == [1, 2]


def test_two_pictures_of_one_card_show_as_one_card_times_two(monkeypatch):
    # Neither picture's epiphany can be read.
    monkeypatch.setattr(guides, "_find_epiphany", lambda *args: None)
    builder = _builder()
    row = guides._number_runs(_row("c_30134_uni2", "c_30134_uni2"))
    for card in row:
        card["picture"] = (_render(), "B1")
    settled = builder._settle_repeats(row, {0: "5/5", 1: "5/5"})
    assert [(card["cardId"], card["count"]) for card in settled] == [("c_30134_uni2", 2)]
    # Different ratings are two different judgements, so both stay.
    assert len(builder._settle_repeats(row, {0: "5/5", 1: "3/5"})) == 2


def test_two_pictures_of_one_card_take_the_levels_they_show(monkeypatch):
    builder = _builder()
    builder.read_text = lambda data: ""

    def find(card_id, download, ref, decks, overrides, read, variants_of):
        return SimpleNamespace(level={"B1": 4, "B2": 1}[ref]), None

    monkeypatch.setattr(guides, "_find_epiphany", find)
    row = guides._number_runs(_row("c_30134_uni2", "c_30134_uni2"))
    row[0]["picture"], row[1]["picture"] = (None, "B1"), (None, "B2")
    assert [card["level"] for card in builder._settle_repeats(row, {0: "5/5", 1: "3/5"})] == [1, 4]


def _render() -> guides._Download:
    return guides._Download(_png(_pattern(5, (123, 183))))


def _card_builder(art: str | None, title: tuple[str | None, float], wide: str | None = None) -> guides._GuideBuilder:
    builder = _builder()
    builder.cards = SimpleNamespace(card_id=lambda picture, data: art, card_ids={"x": "c_1_srt4"})
    builder.sift_cards = SimpleNamespace(match=lambda picture, data: None)
    builder.titles = SimpleNamespace(match=lambda data, own: title)
    builder.sift_wide = SimpleNamespace(match=lambda picture, data: wide)
    return builder


def test_card_keeps_the_art_id_when_the_title_names_the_same_base_card():
    # A title only names the base card, so it must not replace the exact epiphany id the art found.
    assert _card_builder("c_1_srt4_rsp1", ("c_1_srt4", 1.0))._card(_render()) == "c_1_srt4_rsp1"


def test_card_takes_a_trusted_title_over_art_of_another_card():
    assert _card_builder("c_1_srt4", ("c_2_tut1", 0.95))._card(_render()) == "c_2_tut1"
    assert _card_builder("c_1_srt4", ("c_2_tut1", 0.85))._card(_render()) == "c_1_srt4"


def test_card_without_art_uses_the_title_then_the_wide_pool():
    assert _card_builder(None, ("c_2_tut1", 0.85), "c_9")._card(_render()) == "c_2_tut1"
    assert _card_builder(None, (None, 0.0), "c_9")._card(_render()) == "c_9"


def test_guesses_are_collected_for_the_qc_report():
    filled = []
    row = _row("c_30134_uni2", "c_30134_uni2", None, "c_30134_uni2", "c_30134_uni2")
    row[2]["picture"] = (None, "Tab!D5")
    guides._fill_unread(row, _variants_of, filled)
    assert filled == ["Tab!D5"]
    by_position = []
    cards = _flow_list()
    guides._attach_notes([cards, _prose("Zap 1: one\nZap 2: two")], by_position)
    assert by_position == ["Zap 1: one", "Zap 2: two"]
    builder = _builder(picture_size=(123, 120))
    builder.sections(_grid(_cell(20, 1, pictures=1)))
    assert builder.dropped_icons == ["Tab!B21"]
