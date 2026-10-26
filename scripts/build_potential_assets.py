"""
One-off: build the potentials tree assets from the in-game screenshots.

Reads Rita's clean tree (`23.png`) plus the health, attack and defense node crops (`24.png`, `25.png`, `26.png`), and writes the clean tree and the
five node icon glyphs into `scripts/datagen/data/`. The node map (`potentials_nodes.json`) is hand-measured and not written here.

Usage: python -m scripts.build_potential_assets <folder holding the screenshots>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DATA_DIR = Path(__file__).resolve().parent / "datagen" / "data"
ICON_DIR = DATA_DIR / "potential_icons"
# The tree is cut this many pixels in from the left edge, which drops the game's black button and a stray label.
LEFT_CUT = 20
# Background colour of the tree, used to hide the character art that overlaps the lower right.
BACKGROUND = (243, 245, 246)
# Corners of the area to blank, in screenshot pixels. It follows the character art.
ART_POLYGON = [(800, 470), (986, 440), (986, 918), (650, 918), (700, 770), (790, 640)]
# Glyph colour, matching the grey icons on the clean tree.
GLYPH_COLOUR = (112, 114, 120)
# Icon -> (screenshot, node centre in it, glyph is light on a dark node, glyph radius to keep).
ICONS = {
    "crit_chance": ("23.png", (596, 387), False, 30),
    "crit_damage": ("23.png", (855, 356), False, 30),
    "health": ("24.png", (100, 76), False, 24),
    "attack": ("25.png", (81, 63), True, 24),
    "defense": ("26.png", (94, 66), True, 24),
}


def clean_tree(source: Image.Image) -> Image.Image:
    """
    Crop the tree and blank the character art.

    Args:
        source: Rita's tree screenshot.

    Returns:
        The clean tree.
    """
    image = source.convert("RGB").crop((LEFT_CUT, 0, source.width, source.height))
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).polygon([(x - LEFT_CUT, y) for x, y in ART_POLYGON], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(10))
    image.paste(Image.new("RGB", image.size, BACKGROUND), (0, 0), mask)
    return image


def glyph(source: Image.Image, centre: tuple[int, int], light: bool, reach: int) -> Image.Image:
    """
    Cut a node's icon out as a grey glyph with transparency.

    Args:
        source: The screenshot or crop.
        centre: The node centre in it.
        light: True when the glyph is light on a dark node, false when it is dark on a light node.
        reach: How far from the centre to keep.

    Returns:
        A square RGBA glyph, trimmed to its drawn pixels.
    """
    grey = np.asarray(source.convert("L"), dtype=float)
    ys, xs = np.mgrid[0 : grey.shape[0], 0 : grey.shape[1]]
    inside = (xs - centre[0]) ** 2 + (ys - centre[1]) ** 2 <= reach**2
    alpha = np.clip((grey - 150) / 80, 0, 1) if light else np.clip((215 - grey) / 90, 0, 1)
    alpha = np.where(inside, alpha, 0)
    rgba = np.zeros((*grey.shape, 4), dtype=np.uint8)
    rgba[..., :3] = GLYPH_COLOUR
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    image = Image.fromarray(rgba)
    return image.crop(image.getbbox())


def main(folder: Path) -> None:
    """
    Write the clean tree and the icon glyphs.

    Args:
        folder: The folder holding `23.png` to `26.png`.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    clean_tree(Image.open(folder / "23.png")).save(DATA_DIR / "potentials_tree.png", optimize=True)
    for name, (file, centre, light, reach) in ICONS.items():
        glyph(Image.open(folder / file), centre, light, reach).save(ICON_DIR / f"{name}.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
