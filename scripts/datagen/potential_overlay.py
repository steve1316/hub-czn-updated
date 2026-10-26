"""
Potentials tree overlay: read the colour of each node on a guide author's tree picture, and draw it as a ring on the clean tree.

Node positions are fractions (0..1) of the picture width and height, so one map fits the clean tree and every author picture that shows the same crop.
"""

from __future__ import annotations

import colorsys
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

# An author picture smaller than this on either side is too small to sample.
MIN_SAMPLE_SIZE = 64
# A colour needs at least this saturation and brightness to count as a ring, so grey and dark pixels read as no colour.
MIN_SATURATION = 0.35
MIN_VALUE = 0.35
# Hue ranges in degrees.
_HUES = {"purple": (250, 320), "gold": (30, 70), "blue": (190, 250)}
# Ring colours drawn on the clean tree.
RING_COLOURS = {"purple": (192, 132, 252), "gold": (250, 204, 21), "blue": (59, 130, 246)}


@dataclass
class NodeMap:
    """Where each potential node sits on the clean tree."""

    # Node radius as a fraction of the picture width.
    radius: float
    # Node centres as (x, y) fractions of the picture width and height.
    nodes: list[tuple[float, float]]

    @classmethod
    def load(cls, path: Path) -> NodeMap:
        """
        Read a node map from JSON, shaped `{"radius": 0.02, "nodes": [[x, y], ...]}`.

        Args:
            path: The JSON file.

        Returns:
            The node map.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(radius=raw["radius"], nodes=[(x, y) for x, y in raw["nodes"]])


def classify(rgb: tuple[int, int, int]) -> str | None:
    """
    Name a colour as `purple`, `gold` or `blue`.

    Args:
        rgb: The red, green and blue values, 0 to 255.

    Returns:
        The colour name, or None for grey, dark or any other colour.
    """
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb[:3]))
    if s < MIN_SATURATION or v < MIN_VALUE:
        return None
    degrees = h * 360
    for name, (low, high) in _HUES.items():
        if low <= degrees < high:
            return name
    return None


def sample(author: Image.Image, nodes: NodeMap) -> list[str | None] | None:
    """
    Read the colour at each node of the author's picture.

    Args:
        author: The author's tree picture.
        nodes: The node map.

    Returns:
        One colour name or None per node, or None when the picture is too small to sample.
    """
    if min(author.size) < MIN_SAMPLE_SIZE:
        return None
    image = author.convert("RGB")
    width, height = image.size
    reach = max(1, round(nodes.radius * width * 0.5))
    result: list[str | None] = []
    for x, y in nodes.nodes:
        cx, cy = round(x * width), round(y * height)
        votes: dict[str, int] = {}
        for px in range(max(0, cx - reach), min(width, cx + reach + 1)):
            for py in range(max(0, cy - reach), min(height, cy + reach + 1)):
                name = classify(image.getpixel((px, py)))
                if name:
                    votes[name] = votes.get(name, 0) + 1
        result.append(max(votes, key=votes.get) if votes else None)
    return result


def draw(clean: Image.Image, nodes: NodeMap, colours: list[str | None]) -> Image.Image:
    """
    Draw a ring around each coloured node on a copy of the clean tree.

    Args:
        clean: The clean tree picture.
        nodes: The node map.
        colours: One colour name or None per node, from `sample()`.

    Returns:
        The tree with rings.
    """
    out = clean.convert("RGBA")
    pen = ImageDraw.Draw(out)
    width, height = out.size
    radius = nodes.radius * width
    for (x, y), name in zip(nodes.nodes, colours):
        if name not in RING_COLOURS:
            continue
        cx, cy = x * width, y * height
        pen.ellipse([cx - radius * 1.6, cy - radius * 1.6, cx + radius * 1.6, cy + radius * 1.6], outline=RING_COLOURS[name], width=max(1, round(radius * 0.4)))
    return out


def overlay(tree_path: Path, map_path: Path, author: Image.Image | None) -> tuple[Image.Image, bool] | None:
    """
    Build one character's tree picture.

    Args:
        tree_path: The clean tree picture.
        map_path: The node map JSON.
        author: The author's tree picture, or None when the guide has none.

    Returns:
        The tree and whether it has colours, or None when the clean tree or the node map has not been added yet.
        A missing or too small author picture gives the clean tree with False.
    """
    if not tree_path.exists() or not map_path.exists():
        return None
    clean = Image.open(tree_path)
    nodes = NodeMap.load(map_path)
    colours = sample(author, nodes) if author is not None else None
    if colours is None:
        return clean.convert("RGBA"), False
    return draw(clean, nodes, colours), True
