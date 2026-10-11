"""
Identify the pictures in the Guides sheet using the game's own art.

Character faces in the sheet are the game's face portraits, so a perceptual hash finds them exactly. Cards are full
in-game card renders with a frame, name and text drawn over the art, so they are matched by sliding the bare client
illustration under the render's art window and keeping the best fit. Only a clear winner counts. Anything ambiguous is
reported rather than guessed.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import TypeVar

from PIL import Image, ImageChops, ImageStat

# The face portraits the sheet uses, and the ids they carry.
_FACE_FILE = re.compile(r"^shortcut_face_character_(\d+)(?:_\d+)?$")

# A face match must be this close (out of 256 bits) and beat the next character by this much.
FACE_MAX_DISTANCE = 24
FACE_MIN_MARGIN = 16

# A card render's art window, in the sheet's 133x198 render: below the title bar and above the text box.
CARD_RENDER_SIZE = (133, 198)
CARD_ART_WINDOW = (12, 30, 121, 100)
# Illustration widths and vertical offsets tried when lining the art up with the render.
CARD_SCALES = (133, 150, 170)
CARD_OFFSETS = range(-30, 31, 3)
# The best card must beat the runner-up by this much mean pixel difference (0-255).
CARD_MIN_MARGIN = 8

# What a matcher ranks: a res_id for faces, an illustration name for cards.
_Key = TypeVar("_Key")


def load(data: bytes) -> Image.Image:
    """
    Decode an image and flatten any transparency onto black, the way the sheet shows it.

    Args:
        data: The encoded image.

    Returns:
        An RGB image.
    """
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    background = Image.new("RGBA", image.size, (0, 0, 0, 255))
    background.alpha_composite(image)
    return background.convert("RGB")


def kind(image: Image.Image) -> str:
    """
    What a sheet picture probably shows, from its shape.

    Args:
        image: The picture.

    Returns:
        "face" for a small square portrait, "card" for a card-shaped render, otherwise "other".
    """
    width, height = image.size
    if width == height and width <= 128:
        return "face"
    if width and 1.4 <= height / width <= 1.6:
        return "card"
    return "other"


def _clear_winner(scores: dict[_Key, float], *, margin: float, max_distance: float | None = None) -> _Key | None:
    """
    The best-scoring key, only when it clearly beats the rest.

    Args:
        scores: Key -> distance, where lower is better.
        margin: How far ahead of the runner-up the best key must be.
        max_distance: The best key must also be at most this far, or any distance when None.

    Returns:
        The winning key, or None when there are no scores or the best one is not a clear winner.
    """
    ranked = sorted(scores.items(), key=lambda item: item[1])
    if not ranked or (max_distance is not None and ranked[0][1] > max_distance):
        return None
    if len(ranked) > 1 and ranked[1][1] - ranked[0][1] < margin:
        return None
    return ranked[0][0]


def dhash(image: Image.Image, size: int = 16) -> int:
    """
    A difference hash: which neighbouring pixels get brighter, in a small greyscale copy.

    Args:
        image: The picture.
        size: The hash is `size` x `size` bits.

    Returns:
        The hash as an integer.
    """
    pixels = list(image.convert("L").resize((size + 1, size), Image.LANCZOS).getdata())
    bits = 0
    for y in range(size):
        for x in range(size):
            bits = (bits << 1) | (pixels[y * (size + 1) + x] > pixels[y * (size + 1) + x + 1])
    return bits


class FaceMatcher:
    """Finds which character a face portrait shows."""

    def __init__(self, face_dir: Path):
        """
        Args:
            face_dir: The client's `face/character` folder.
        """
        self._hashes: list[tuple[int, int]] = []
        for path in sorted(face_dir.glob("shortcut_face_character_*.png")):
            match = _FACE_FILE.match(path.stem)
            if match:
                self._hashes.append((int(match.group(1)), dhash(load(path.read_bytes()))))

    def match(self, image: Image.Image, hash_value: int | None = None) -> int | None:
        """
        The character a portrait shows.

        Args:
            image: The sheet's picture.
            hash_value: The picture's `dhash`, when the caller already has it.

        Returns:
            The character's res_id, or None when no character is a clear match.
        """
        target = dhash(image) if hash_value is None else hash_value
        best: dict[int, int] = {}
        for res_id, value in self._hashes:
            distance = (target ^ value).bit_count()
            best[res_id] = min(distance, best.get(res_id, distance))
        return _clear_winner(best, margin=FACE_MIN_MARGIN, max_distance=FACE_MAX_DISTANCE)


class CardMatcher:
    """Finds which illustration a card render shows, among a small set of candidates."""

    def __init__(self, candidates: dict[str, Path]):
        """
        Args:
            candidates: Illustration name -> its PNG in the client's `card_illustration` folder.
        """
        self._windows: list[tuple[str, Image.Image]] = []
        left, top, right, bottom = CARD_ART_WINDOW
        for name, path in sorted(candidates.items()):
            art = load(path.read_bytes())
            for scale in CARD_SCALES:
                scaled = art.resize((scale, round(scale * art.height / art.width)))
                x_shift = (scale - CARD_RENDER_SIZE[0]) // 2
                y_base = (scaled.height - CARD_RENDER_SIZE[1]) // 2
                for offset in CARD_OFFSETS:
                    box = (left + x_shift, top + y_base + offset, right + x_shift, bottom + y_base + offset)
                    if box[1] >= 0 and box[3] <= scaled.height:
                        self._windows.append((name, scaled.crop(box)))

    def match(self, image: Image.Image) -> str | None:
        """
        The illustration a render shows.

        Args:
            image: The sheet's card render.

        Returns:
            The illustration name, or None when no candidate is a clear winner.
        """
        window = image.resize(CARD_RENDER_SIZE).crop(CARD_ART_WINDOW)
        best: dict[str, float] = {}
        for name, candidate in self._windows:
            difference = sum(ImageStat.Stat(ImageChops.difference(window, candidate)).mean) / 3
            best[name] = min(difference, best.get(name, difference))
        return _clear_winner(best, margin=CARD_MIN_MARGIN)
