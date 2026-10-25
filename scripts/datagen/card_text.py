"""
Which epiphany a guide card picture shows, read from its text box with OCR, and which god's emblem sits under its cost.

The sheet's card renders all share their base card's art, so the art cannot tell epiphanies apart but the text can. The
OCR text is compared with every level's own text, alone and with one added divine or common line, and only a clear
winner is taken. Calibrated on the Rossweisse tab, where it reads all eight deck cards right.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import re
from dataclasses import dataclass
from functools import cache

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from scripts.datagen.epiphany import EPIPHANY_DATA_DIR, Extra, Variant, divine_gods

# The size the sheet renders a card at. Pictures are scaled to it before the emblem is looked for.
RENDER_SIZE = (123, 183)
# The card text box is the lower part of the render. It is upscaled before OCR, which reads small text far better.
TEXT_TOP = 0.55
OCR_SCALE = 3

# Where the emblem sits on a render, under the cost: the regular target mark, or a god's emblem for a divine epiphany.
EMBLEM_BOX = (0, 22, 32, 60)
EMBLEM_SIZES = range(18, 29, 2)
# Mean colour difference (0-255) over the icon's opaque pixels. Gods' emblems scored 20-29 and regular marks 45 and up.
MAX_EMBLEM_DIFF = 38
EMBLEM_MARGIN = 12
GOD_ICON_DIR = EPIPHANY_DATA_DIR / "divine-gods"

# The winner's letters-only score must reach this, and beat every other level's best by a margin on letters or on digits.
MIN_SCORE = 0.75
LETTER_MARGIN = 0.05
DIGIT_MARGIN = 0.02

_engine = None


@dataclass(frozen=True)
class Match:
    """The epiphany a card picture was matched to."""

    # 0 for the base card, else the epiphany level.
    level: int
    # The divine or common line added to the card, if any.
    extra: Extra | None


def read_card_text(data: bytes, cache: dict[str, str]) -> str:
    """
    The text on a card picture.

    Args:
        data: The picture file.
        cache: sha1 of the picture -> its text, from earlier runs. Updated in place.

    Returns:
        The OCR text of the card's text box, one space between the lines it found.
    """
    key = hashlib.sha1(data).hexdigest()
    if key not in cache:
        picture = Image.open(io.BytesIO(data)).convert("RGB")
        width, height = picture.size
        big = picture.resize((width * OCR_SCALE, height * OCR_SCALE), Image.LANCZOS)
        result, _ = _ocr()(np.asarray(big.crop((0, int(big.height * TEXT_TOP), big.width, big.height))))
        cache[key] = " ".join(line[1] for line in result or [])
    return cache[key]


def match_epiphany(text: str, variants: list[Variant], extras: list[Extra]) -> Match | None:
    """
    The level, and any added line, whose text best matches a card's OCR text.

    Args:
        text: The OCR text.
        variants: The card at every level, from `epiphany.variants`.
        extras: The lines the card may carry: the god's divine epiphanies when it shows a god's emblem, else the common ones.

    Returns:
        The match, or None when no candidate scores well enough or another level comes too close.
    """
    letters, digits = _letters(text), _digits(text)
    scored = []
    for variant in variants:
        for extra in [None, *extras]:
            candidate = variant.text if extra is None else f"{variant.text} {extra.text}"
            letter_score = round(difflib.SequenceMatcher(None, letters, _letters(candidate)).ratio(), 2)
            digit_score = difflib.SequenceMatcher(None, digits, _digits(candidate)).ratio()
            scored.append((letter_score, digit_score, variant.level, extra))
    if not scored:
        return None
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    best = scored[0]
    if best[0] < MIN_SCORE:
        return None
    other = next((entry for entry in scored if entry[2] != best[2]), None)
    if other and best[0] - other[0] < LETTER_MARGIN and best[1] - other[1] < DIGIT_MARGIN:
        return None
    return Match(best[2], best[3])


def match_god(picture: Image.Image) -> str | None:
    """
    The god whose emblem a card picture shows under its cost.

    Args:
        picture: The card render.

    Returns:
        The god's display name, such as "Nihilum", or None for the regular emblem or an unclear one.
    """
    region = np.asarray(picture.convert("RGB").resize(RENDER_SIZE).crop(EMBLEM_BOX), dtype=float)
    scores = sorted((_emblem_difference(region, sizes), god) for god, sizes in _god_icons().items())
    (best, god), (second, _) = scores[0], scores[1]
    return god if best <= MAX_EMBLEM_DIFF and second - best >= EMBLEM_MARGIN else None


def _emblem_difference(region: np.ndarray, sizes: list[tuple[np.ndarray, np.ndarray]]) -> float:
    """The smallest mean colour difference between the icon and any spot in the region, over the icon's sizes."""
    best = float("inf")
    for colour, alpha in sizes:
        windows = sliding_window_view(region, colour.shape)[:, :, 0]
        difference = (np.abs(windows - colour) * alpha).sum(axis=(2, 3, 4)) / (alpha.sum() * 3)
        best = min(best, float(difference.min()))
    return best


@cache
def _god_icons() -> dict[str, list[tuple[np.ndarray, np.ndarray]]]:
    """Each god's display name -> its emblem icon at every size in `EMBLEM_SIZES`, as (colour, alpha 0-1) arrays."""
    icons = {}
    for stem, display in divine_gods().items():
        icon = Image.open(GOD_ICON_DIR / f"{stem}.webp").convert("RGBA")
        pixels = [np.asarray(icon.resize((size, size), Image.LANCZOS), dtype=float) for size in EMBLEM_SIZES]
        icons[display] = [(sized[..., :3], sized[..., 3:] / 255) for sized in pixels]
    return icons


def _ocr():
    """The OCR engine, built once. RapidOCR is only needed by the Guides import, so it is imported here."""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _digits(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())
