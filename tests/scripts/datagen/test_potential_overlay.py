"""Tests for the potentials tree overlay: sampling the author's colours and drawing rings on the clean tree."""

from PIL import Image

from scripts.datagen import potential_overlay as po

NODES = po.NodeMap(radius=0.05, nodes=[(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)])


def _author(size: int, colours: list[tuple[int, int, int]]) -> Image.Image:
    """A dark picture with a coloured dot at each node of `NODES`."""
    image = Image.new("RGB", (size, size), (20, 20, 20))
    for (x, y), colour in zip(NODES.nodes, colours):
        cx, cy, r = round(x * size), round(y * size), round(NODES.radius * size)
        for px in range(cx - r, cx + r + 1):
            for py in range(cy - r, cy + r + 1):
                image.putpixel((px, py), colour)
    return image


def test_classify_colours():
    assert po.classify((170, 60, 220)) == "purple"
    assert po.classify((230, 190, 50)) == "gold"
    assert po.classify((50, 110, 230)) == "blue"
    assert po.classify((20, 20, 20)) is None
    assert po.classify((128, 128, 128)) is None


def test_sample_reads_each_node():
    author = _author(200, [(170, 60, 220), (230, 190, 50), (50, 110, 230), (20, 20, 20)])
    assert po.sample(author, NODES) == ["purple", "gold", "blue", None]


def test_sample_refuses_tiny_pictures():
    author = _author(20, [(170, 60, 220)] * 4)
    assert po.sample(author, NODES) is None


def test_draw_rings_only_coloured_nodes():
    clean = Image.new("RGB", (200, 200), (0, 0, 0))
    out = po.draw(clean, NODES, ["purple", None, "gold", "blue"])
    assert out.size == clean.size
    # The ring sits 14 px right of the first node's centre (50, 50), and the second node (150, 50) has no colour.
    assert out.getpixel((64, 50))[:3] == po.RING_COLOURS["purple"]
    assert out.getpixel((164, 50))[:3] == (0, 0, 0)
    assert clean.getpixel((64, 50)) == (0, 0, 0)


def test_overlay_without_assets_returns_none(tmp_path):
    assert po.overlay(tmp_path / "missing.png", tmp_path / "missing.json", Image.new("RGB", (100, 100))) is None
