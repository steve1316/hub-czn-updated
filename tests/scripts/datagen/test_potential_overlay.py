"""Tests for the potentials tree overlay: registering an author picture to the clean tree, sampling its ring colours, and drawing them back."""

import numpy as np
from PIL import Image, ImageDraw

from scripts.datagen import potential_overlay as po

CLEAN = Image.open(po.TREE_PATH).convert("RGB")
NODES = po.NodeMap.load(po.NODES_PATH)


def _author(rings: dict[str, tuple[int, int, int]], scale: float = 0.38, crop: tuple[int, int, int, int] = (0, 0, 0, 0)) -> Image.Image:
    """The clean tree shrunk like an author's screenshot and cropped by `crop` (left, top, right, bottom), with a coloured ring on each given node."""
    big = CLEAN.copy()
    pen = ImageDraw.Draw(big)
    for label, colour in rings.items():
        cx, cy, r = NODES.centre(label, big.size)
        pen.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colour, width=9)
    small = big.resize((round(big.width * scale), round(big.height * scale)), Image.LANCZOS)
    left, top, right, bottom = crop
    return small.crop((left, top, small.width - right, small.height - bottom))


def test_node_labels_follow_the_database_numbering():
    assert po.node_label("1_0") == "01"
    assert po.node_label("5_0") == "05"
    assert po.node_label("3_1") == "03-1"
    assert po.node_label("5_2") == "05-2"


def test_node_map_has_every_node_of_the_game():
    assert sorted(NODES.nodes) == ["01", "02", "03", "03-1", "04", "05", "05-1", "05-2", "06", "07"]


def test_variant_icons_follow_the_node_types():
    rows = [
        {"link_char_combatant_id": "1", "node_level": "1", "node_num": "5_0", "link_potential_node_type_define_id": "N_ADD_S_HP_INC_RATE_OUT"},
        {"link_char_combatant_id": "1", "node_level": "1", "node_num": "6_0", "link_potential_node_type_define_id": "N_ADD_S_DEF_INC_RATE_OUT"},
        {"link_char_combatant_id": "1", "node_level": "2", "node_num": "6_0", "link_potential_node_type_define_id": "N_ADD_S_ATK_INC_RATE_OUT"},
        {"link_char_combatant_id": "2", "node_level": "1", "node_num": "5_0", "link_potential_node_type_define_id": "N_ADD_S_CRI_INC_ADD"},
    ]
    assert po.variant_icons(rows, "1") == {"05": "health", "06": "defense"}
    assert po.variant_icons(rows, "2") == {"05": "crit_chance"}


def test_classify_colours():
    assert po.classify((170, 60, 190)) == "purple"
    assert po.classify((240, 200, 40)) == "gold"
    assert po.classify((40, 150, 230)) == "blue"
    assert po.classify((240, 140, 40)) is None
    assert po.classify((20, 20, 20)) is None
    assert po.classify((200, 200, 205)) is None


def test_register_finds_a_shrunk_and_cropped_picture():
    author = _author({}, crop=(30, 10, 5, 0))
    found = po.register(author)
    assert found is not None
    # Clean (0, 0) lands at the crop's offset, and the picture is ~0.38 the size.
    cx, cy, _ = NODES.centre("04", CLEAN.size)
    mapped = found @ np.array([cx, cy, 1.0])
    assert abs(mapped[0] - (cx * 0.38 - 30)) < 3
    assert abs(mapped[1] - (cy * 0.38 - 10)) < 3


def test_register_refuses_a_picture_that_is_not_the_tree():
    rng = np.random.default_rng(1)
    noise = Image.fromarray(rng.integers(0, 255, (300, 300, 3), dtype=np.uint8))
    assert po.register(noise) is None
    assert po.register(Image.new("RGB", (23, 20), "white")) is None


def test_sample_reads_ring_colours_from_a_cropped_picture():
    author = _author({"04": (170, 60, 190), "05": (240, 200, 40), "03": (40, 150, 230)}, crop=(25, 15, 10, 20))
    colours = po.sample(author)
    assert colours is not None
    assert colours["04"] == "purple"
    assert colours["05"] == "gold"
    assert colours["03"] == "blue"
    assert colours["07"] is None


def test_sample_gives_nothing_for_a_tiny_picture():
    assert po.sample(Image.new("RGB", (23, 20), "white")) is None


def test_draw_rings_coloured_nodes_and_swaps_the_variant_icon():
    out = po.draw(CLEAN, NODES, {"04": "purple", "05": None}, {"05": "health"})
    cx, cy, r = NODES.centre("04", CLEAN.size)
    assert out.getpixel((round(cx + r - 2), round(cy)))[:3] == po.RING_COLOURS["purple"]
    assert out.size == CLEAN.size
    assert out.getpixel((round(NODES.centre("07", CLEAN.size)[0]), 5))[:3] == CLEAN.getpixel((round(NODES.centre("07", CLEAN.size)[0]), 5))
    # The node 05 icon differs from the clean tree once health replaces it.
    x, y, _ = NODES.centre("05", CLEAN.size)
    box = (round(x - 20), round(y - 20), round(x + 20), round(y + 20))
    assert np.abs(np.asarray(out.convert("RGB").crop(box), dtype=int) - np.asarray(CLEAN.crop(box), dtype=int)).sum() > 5000


def test_build_falls_back_to_the_clean_tree_without_colours():
    tree, coloured = po.build(Image.new("RGB", (23, 20), "white"), {})
    assert coloured is False
    assert tree.size == CLEAN.size
    tree, coloured = po.build(None, {})
    assert coloured is False


def test_build_uses_hand_marked_colours_over_the_picture():
    tree, coloured = po.build(None, {}, {"04": "gold"})
    assert coloured is True
    cx, cy, r = NODES.centre("04", CLEAN.size)
    assert tree.convert("RGB").getpixel((round(cx + r - 2), round(cy))) == po.RING_COLOURS["gold"]


def test_build_colours_a_registered_picture():
    tree, coloured = po.build(_author({"04": (170, 60, 190)}), {"05": "crit_chance", "06": "crit_damage"})
    assert coloured is True
    cx, cy, r = NODES.centre("04", CLEAN.size)
    assert tree.convert("RGB").getpixel((round(cx + r - 2), round(cy))) == po.RING_COLOURS["purple"]
