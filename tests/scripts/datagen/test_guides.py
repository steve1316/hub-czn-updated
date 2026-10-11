"""
Tests for the Guides import: the sheet's HTML grid, splitting a tab into sections, picture labels and the image matchers.
Everything runs on synthetic inputs, so no network or extracted client is needed.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from scripts.datagen import images, naming
from scripts.datagen.sheet import Cell, column_letters, parse_grid, tabs
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


def test_slugs_ids_and_identifiers():
    assert naming.slug("Mei Lin") == "mei-lin"
    assert naming.slug("A" * 47 + " b", 48) == "a" * 47
    used: set[str] = set()
    assert [guides._unique("part", used) for _ in range(3)] == ["part", "part-2", "part-3"]
    assert guides._identifier("mei-lin") == "meiLinJson"


def test_content_module_imports_every_guide_in_order():
    module = guides._content_module([("mei-lin", "Mei Lin"), ("nia", "Nia")]).decode("utf-8")
    assert "import meiLinJson from './data/mei-lin.guide.json'" in module
    assert module.index("meiLinJson as Guide") < module.index("niaJson as Guide")
    assert "export function getGuide" in module


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
    render = arts["unique_1_02"].resize(images.CARD_RENDER_SIZE)
    draw = ImageDraw.Draw(render)
    draw.rectangle((0, 0, 132, 25), fill=(20, 20, 20))
    draw.rectangle((0, 110, 132, 197), fill=(20, 20, 20))
    assert matcher.match(render) == "unique_1_02"
