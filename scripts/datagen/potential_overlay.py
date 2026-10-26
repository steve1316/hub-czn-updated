"""
Potentials tree overlay: read the colour of each node ring on a guide author's tree picture, and draw it on one clean tree.

The author's picture is first registered to the clean tree with SIFT, so it can be any size or crop. Each node's position is then known and its ring colour is read.
A picture that is too small or does not register gets the clean tree with no colours.
"""

from __future__ import annotations

import colorsys
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

DATA_DIR = Path(__file__).resolve().parent / "data"
TREE_PATH = DATA_DIR / "potentials_tree.png"
NODES_PATH = DATA_DIR / "potentials_nodes.json"
ICON_DIR = DATA_DIR / "potential_icons"

# An author picture smaller than this on either side is too small to register.
MIN_SIZE = 64
# The picture is enlarged to this width before matching, since the author's pictures are small.
MATCH_WIDTH = 760
# Registration needs this many SIFT matches that agree, and an author picture scale (its size over the clean tree's) within this range.
MIN_INLIERS = 12
SCALE_RANGE = (0.15, 1.5)
# The clean tree is matched at these sizes (1 is full size).
CLEAN_SCALES = (1.0, 0.75, 0.55)
# SIFT descriptor ratio test and the pixel error a match may have after registration.
RATIO = 0.9
RANSAC_ERROR = 6
# How far apart (in the enlarged picture, in pixels) two matches' offsets may be to vote together.
OFFSET_TOLERANCE = 25
# How far a match's feature size ratio may stray from the median one, as a natural log.
SIZE_SPREAD = 0.3
# A colour needs at least this saturation and brightness to count as a ring, so grey and dark pixels read as no colour.
MIN_SATURATION = 0.3
MIN_VALUE = 0.3
# Hue ranges in degrees.
HUES = {"purple": (250, 335), "gold": (38, 70), "blue": (185, 250)}
# The ring is read between these fractions of a node's radius, in this many steps with this many samples each. A node needs this share of one circle to agree on a colour.
RING_BAND = (0.65, 1.1)
RING_STEPS = 19
ANGLES = 72
MIN_SHARE = 0.25
# A node needs this share of its circle inside the picture to be read at all.
MIN_VISIBLE = 0.3
# Ring colours drawn on the clean tree, the same as the legend in the guide page.
RING_COLOURS = {"purple": (192, 132, 252), "gold": (250, 204, 21), "blue": (96, 165, 250)}
# Node type -> icon name, for the two nodes whose stat differs per character.
VARIANT_TYPES = {
    "N_ADD_S_CRI_INC_ADD": "crit_chance",
    "N_ADD_S_CRI_DMG_RATE_INC_ADD": "crit_damage",
    "N_ADD_S_HP_INC_RATE_OUT": "health",
    "N_ADD_S_ATK_INC_RATE_OUT": "attack",
    "N_ADD_S_DEF_INC_RATE_OUT": "defense",
}
# The node labels that carry a variant icon, which the clean tree draws as crit chance and crit damage.
VARIANT_LABELS = ("05", "06")
# How far from a node's centre its icon is blanked out before the new one is pasted, as a fraction of its radius.
ICON_CLEAR = 0.5


@dataclass
class NodeMap:
    """Where each potential node sits on the clean tree."""

    # Node label (`01`, `03-1`, ...) -> its centre as fractions of the picture width and height, and its radius as a fraction of the width.
    nodes: dict[str, tuple[float, float, float]]

    @classmethod
    def load(cls, path: Path) -> NodeMap:
        """
        Read the node map, shaped `{"nodes": {"03-1": {"x": 0.6, "y": 0.6, "r": 0.08}}}`.

        Args:
            path: The JSON file.

        Returns:
            The node map.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls({label: (node["x"], node["y"], node["r"]) for label, node in raw["nodes"].items()})

    def centre(self, label: str, size: tuple[int, int]) -> tuple[float, float, float]:
        """
        A node's centre and radius in pixels.

        Args:
            label: The node label.
            size: The tree picture's width and height.

        Returns:
            The x, y and radius in pixels.
        """
        x, y, r = self.nodes[label]
        return x * size[0], y * size[1], r * size[0]


def node_label(node_num: str) -> str:
    """
    The label the game draws next to a node.

    Args:
        node_num: The database `node_num`, such as `3_1`.

    Returns:
        The label, such as `03-1`. The first node of a row, `5_0`, is just `05`.
    """
    row, step = node_num.split("_")
    return f"{int(row):02d}" + (f"-{step}" if step != "0" else "")


def variant_icons(rows: list[dict], char_id: str) -> dict[str, str]:
    """
    The icon each stat node of a character shows.

    Args:
        rows: The rows of `potential_node@potential_node.json`.
        char_id: The character's combatant id.

    Returns:
        Node label -> icon name, for the nodes in `VARIANT_LABELS` that the character has.
    """
    found = {}
    for row in rows:
        if row["link_char_combatant_id"] != char_id or row["node_level"] != "1":
            continue
        label = node_label(row["node_num"])
        if label in VARIANT_LABELS and row["link_potential_node_type_define_id"] in VARIANT_TYPES:
            found[label] = VARIANT_TYPES[row["link_potential_node_type_define_id"]]
    return found


def classify(rgb: tuple[int, int, int]) -> str | None:
    """
    Name a colour as `purple`, `gold` or `blue`.

    Args:
        rgb: The red, green and blue values, 0 to 255.

    Returns:
        The colour name, or None for grey, dark, orange or any other colour.
    """
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb[:3]))
    if s < MIN_SATURATION or v < MIN_VALUE:
        return None
    degrees = h * 360
    for name, (low, high) in HUES.items():
        if low <= degrees < high:
            return name
    return None


@lru_cache(maxsize=1)
def _clean() -> Image.Image:
    return Image.open(TREE_PATH).convert("RGB")


@lru_cache(maxsize=1)
def _nodes() -> NodeMap:
    return NodeMap.load(NODES_PATH)


def _grey(image: Image.Image) -> np.ndarray:
    """Greyscale pixels, enlarged to `MATCH_WIDTH` wide when the picture is smaller."""
    grey = np.asarray(image.convert("L"))
    if grey.shape[1] < MATCH_WIDTH:
        grey = cv2.resize(grey, None, fx=MATCH_WIDTH / grey.shape[1], fy=MATCH_WIDTH / grey.shape[1], interpolation=cv2.INTER_CUBIC)
    return grey


@lru_cache(maxsize=None)
def _clean_features(scale: float):
    """The clean tree's SIFT points, sizes and descriptors, found at `scale` and given in the clean tree's own pixels."""
    clean = _clean().convert("L")
    if scale != 1.0:
        clean = clean.resize((round(clean.width * scale), round(clean.height * scale)), Image.LANCZOS)
    keys, desc = cv2.SIFT_create().detectAndCompute(np.asarray(clean), None)
    return np.float32([key.pt for key in keys]) / scale, np.float32([key.size for key in keys]) / scale, desc


def register(author: Image.Image) -> np.ndarray | None:
    """
    Find where the clean tree sits in an author's picture.

    Args:
        author: The author's tree picture.

    Returns:
        A 2x3 matrix that maps clean tree pixels to the author's pixels, or None when the picture is too small or does not match well enough.
    """
    return fit(author)[0]


def fit(author: Image.Image) -> tuple[np.ndarray | None, int]:
    """
    Register an author's picture and count the matches that support it. The clean tree is tried at a few sizes, as SIFT matches best at similar sizes.

    Args:
        author: The author's tree picture.

    Returns:
        The matrix of `register()` or None, and the number of SIFT matches that agree with it.
    """
    if min(author.size) < MIN_SIZE:
        return None, 0
    grey = _grey(author)
    keys, desc = cv2.SIFT_create().detectAndCompute(grey, None)
    if desc is None or len(keys) < 2:
        return None, 0
    points, sizes = np.float32([key.pt for key in keys]), np.float32([key.size for key in keys])
    best: tuple[np.ndarray | None, int] = (None, 0)
    for scale in CLEAN_SCALES:
        matrix, count = _fit_at(points, sizes, desc, _clean_features(scale))
        if count > best[1]:
            best = (matrix, count)
    matrix, count = best
    if matrix is None:
        return None, count
    # The matrix maps into the enlarged picture, so scale it back to the author's own pixels.
    matrix = matrix * author.width / grey.shape[1]
    scale = math.hypot(matrix[0, 0], matrix[1, 0])
    return (matrix if SCALE_RANGE[0] <= scale <= SCALE_RANGE[1] else None), count


def _fit_at(points: np.ndarray, sizes: np.ndarray, desc: np.ndarray, clean: tuple) -> tuple[np.ndarray | None, int]:
    """Match the author's SIFT features to one set of clean features and fit the transform that most matches agree on."""
    clean_points, clean_sizes, clean_desc = clean
    if len(clean_points) < 2:
        return None, 0
    good = [pair[0] for pair in cv2.BFMatcher().knnMatch(clean_desc, desc, k=2) if len(pair) == 2 and pair[0].distance < RATIO * pair[1].distance]
    if len(good) < MIN_INLIERS:
        return None, 0
    # Keep the matches whose feature sizes agree on one scale, which drops the false ones that would otherwise collapse the fit.
    ratios = np.array([sizes[m.trainIdx] / clean_sizes[m.queryIdx] for m in good])
    good = [m for m, ratio in zip(good, ratios) if abs(math.log(ratio / np.median(ratios))) < SIZE_SPREAD]
    if len(good) < MIN_INLIERS:
        return None, 0
    src = np.float32([clean_points[m.queryIdx] for m in good])
    dst = np.float32([points[m.trainIdx] for m in good])
    # Vote for the offset at the median scale, so false matches that all land on one spot cannot make a degenerate fit. Then fit the voters.
    offsets = dst - np.median(ratios) * src
    votes = [(np.linalg.norm(offsets - offset, axis=1) < OFFSET_TOLERANCE) for offset in offsets]
    voters = max(votes, key=lambda vote: vote.sum())
    if voters.sum() < MIN_INLIERS:
        return None, int(voters.sum())
    matrix, _ = cv2.estimateAffinePartial2D(src[voters], dst[voters], method=cv2.RANSAC, ransacReprojThreshold=RANSAC_ERROR, maxIters=2000)
    if matrix is None:
        return None, 0
    count = int((np.linalg.norm(src @ matrix[:, :2].T + matrix[:, 2] - dst, axis=1) < RANSAC_ERROR).sum())
    return (matrix, count) if count >= MIN_INLIERS else (None, count)


def sample(author: Image.Image) -> dict[str, str | None] | None:
    """
    Read the ring colour of every node on an author's picture.

    Args:
        author: The author's tree picture.

    Returns:
        Node label -> `purple`, `gold`, `blue` or None for no colour, or None when the picture could not be registered.
    """
    matrix = register(author)
    if matrix is None:
        return None
    image = author.convert("RGB")
    pixels = np.asarray(image)
    height, width = pixels.shape[:2]
    clean_size = _clean().size
    scale = math.hypot(matrix[0, 0], matrix[1, 0])
    colours: dict[str, str | None] = {}
    for label in _nodes().nodes:
        cx, cy, r = _nodes().centre(label, clean_size)
        ox, oy = matrix @ np.array([cx, cy, 1.0])
        # The ring sits at a different radius in each author's picture, so keep the radius where one colour fills the most of the circle.
        best, best_share = None, 0.0
        for fraction in np.linspace(RING_BAND[0], RING_BAND[1], RING_STEPS):
            votes: dict[str, int] = {}
            total = 0
            for angle in np.linspace(0, 2 * math.pi, ANGLES, endpoint=False):
                px = round(ox + math.cos(angle) * r * scale * fraction)
                py = round(oy + math.sin(angle) * r * scale * fraction)
                if not (0 <= px < width and 0 <= py < height):
                    continue
                total += 1
                if name := classify(tuple(int(c) for c in pixels[py, px])):
                    votes[name] = votes.get(name, 0) + 1
            if votes and total >= ANGLES * MIN_VISIBLE:
                name = max(votes, key=votes.get)
                if votes[name] / total > best_share:
                    best, best_share = name, votes[name] / total
        colours[label] = best if best_share >= MIN_SHARE else None
    return colours


@lru_cache(maxsize=None)
def _icon(name: str) -> Image.Image:
    return Image.open(ICON_DIR / f"{name}.png").convert("RGBA")


def _swap_icon(image: Image.Image, centre: tuple[float, float], radius: float, name: str) -> None:
    """Blank the icon in the middle of a node and paste another in its place."""
    cx, cy = centre
    ring = np.asarray(image.convert("RGB"), dtype=float)
    edge = [ring[round(cy + math.sin(a) * radius * ICON_CLEAR * 1.1), round(cx + math.cos(a) * radius * ICON_CLEAR * 1.1)] for a in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
    fill = tuple(int(v) for v in np.median(edge, axis=0))
    clear = radius * ICON_CLEAR
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse([cx - clear, cy - clear, cx + clear, cy + clear], fill=255)
    image.paste(Image.new("RGB", image.size, fill), (0, 0), mask)
    glyph = _icon(name)
    image.paste(glyph, (round(cx - glyph.width / 2), round(cy - glyph.height / 2)), glyph)


def draw(clean: Image.Image, nodes: NodeMap, colours: dict[str, str | None], icons: dict[str, str]) -> Image.Image:
    """
    Draw the variant icons and a ring around each coloured node on a copy of the clean tree.

    Args:
        clean: The clean tree picture.
        nodes: The node map.
        colours: Node label -> colour name or None, from `sample()`.
        icons: Node label -> icon name, from `variant_icons()`.

    Returns:
        The tree as RGB.
    """
    out = clean.convert("RGB")
    for label, name in icons.items():
        if label in nodes.nodes:
            cx, cy, r = nodes.centre(label, out.size)
            _swap_icon(out, (cx, cy), r, name)
    pen = ImageDraw.Draw(out)
    for label, name in colours.items():
        if name not in RING_COLOURS or label not in nodes.nodes:
            continue
        cx, cy, r = nodes.centre(label, out.size)
        pen.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RING_COLOURS[name], width=max(3, round(r * 0.09)))
    return out


def build(author: Image.Image | None, icons: dict[str, str]) -> tuple[Image.Image, bool]:
    """
    Build one character's tree picture.

    Args:
        author: The author's tree picture, or None when the guide has none.
        icons: Node label -> icon name for this character, from `variant_icons()`.

    Returns:
        The tree and whether it has colours. A missing, too small or unregistered author picture gives the tree with its icons and no rings.
    """
    colours = sample(author) if author is not None else None
    return draw(_clean(), _nodes(), colours or {}, icons), colours is not None
