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
# The title bar is the top of the render, to the right of the cost gem.
TITLE_BOTTOM = 0.14
TITLE_LEFT = 0.15
TITLE_SCALE = 4

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
# A number the card shows as a percentage, such as "150%".
_PERCENTAGE = re.compile(r"(\d+)\s*%")
# The read may run this much longer than the level it matches by percentages. Longer means an added line it cannot place.
MAX_TEXT_GROWTH = 1.25

_engine = None


@dataclass(frozen=True)
class Match:
    """The epiphany a card picture was matched to."""

    # 0 for the base card, else the epiphany level.
    level: int
    # The divine or common line added to the card, if any.
    extra: Extra | None


def _read_cached(data: bytes, cache: dict[str, str], box: tuple[float, float, float, float], scale: int) -> str:
    """
    The OCR text of part of a card picture, remembered by the picture's hash.

    Args:
        data: The picture file.
        cache: sha1 of the picture -> its text, from earlier runs. Updated in place.
        box: The part to read, as the fractions (left, top, right, bottom) of the picture.
        scale: How much to enlarge the part first, as OCR reads small text far better.

    Returns:
        The OCR text, one space between the lines it found.
    """
    key = hashlib.sha1(data).hexdigest()
    if key not in cache:
        picture = Image.open(io.BytesIO(data)).convert("RGB")
        width, height = picture.size
        left, top, right, bottom = int(width * box[0]), int(height * box[1]), int(width * box[2]), int(height * box[3])
        part = picture.crop((left, top, right, max(bottom, top + 1)))
        big = part.resize((part.width * scale, part.height * scale), Image.LANCZOS)
        result, _ = _ocr()(np.asarray(big))
        cache[key] = " ".join(line[1] for line in result or [])
    return cache[key]


def read_card_text(data: bytes, cache: dict[str, str]) -> str:
    """
    The text on a card picture.

    Args:
        data: The picture file.
        cache: sha1 of the picture -> its text, from earlier runs. Updated in place.

    Returns:
        The OCR text of the card's text box, one space between the lines it found.
    """
    return _read_cached(data, cache, (0.0, TEXT_TOP, 1.0, 1.0), OCR_SCALE)


def read_card_title(data: bytes, cache: dict[str, str]) -> str:
    """
    The name on a card picture's title bar.

    Args:
        data: The picture file.
        cache: sha1 of the picture -> its title, from earlier runs. Updated in place.

    Returns:
        The OCR text of the title bar, one space between the pieces it found, or "" when it read nothing.
    """
    return _read_cached(data, cache, (TITLE_LEFT, 0.0, 1.0, TITLE_BOTTOM), TITLE_SCALE)


def match_epiphany(text: str, variants: list[Variant], extras: list[Extra]) -> Match | None:
    """
    The level, and any added line, whose text best matches a card's OCR text.

    Args:
        text: The OCR text.
        variants: The card at every level, from `epiphany.variants`.
        extras: The lines the card may carry: the god's divine epiphanies when it shows a god's emblem, else the common ones.

    Returns:
        The match, or None when no candidate scores well enough, or another level or another added line comes too close.
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
    other_level = next((entry for entry in scored if entry[2] != best[2]), None)
    if best[0] < MIN_SCORE or (other_level and best[0] - other_level[0] < LETTER_MARGIN and best[1] - other_level[1] < DIGIT_MARGIN):
        # A god's emblem means a divine line is on the card, which the percentages cannot place.
        return None if any(extra.god for extra in extras) else _match_percentages(text, variants)
    # Another line at the same level, such as "Apply 1 Weaken" against "Apply 2 Weaken". One digit barely moves the score, so any
    # digit lead settles it, and no lead means the digit was not read. Lines with the same text are the same read, whatever their
    # ids. No line against a short line is left to the ranking, as they score close even on a clean read.
    other_line = next((entry for entry in scored if best[3] and entry[2] == best[2] and entry[3] and entry[3].text != best[3].text), None)
    if other_line and best[0] - other_line[0] < LETTER_MARGIN and best[1] <= other_line[1]:
        return None
    return Match(best[2], best[3])


def _match_percentages(text: str, variants: list[Variant]) -> Match | None:
    """
    The one level whose percentages are exactly the ones on the card, for older pictures whose wording a patch has since changed.

    Args:
        text: The OCR text.
        variants: The card at every level.

    Returns:
        The match with no added line. None when the card shows no percentages, not exactly one level has them, or the read runs
        well past that level's text.
    """
    shown = _percentages(text)
    if not shown:
        return None
    fits = [variant for variant in variants if _percentages(variant.text) == shown]
    if len(fits) != 1 or len(_letters(text)) > len(_letters(fits[0].text)) * MAX_TEXT_GROWTH:
        return None
    return Match(fits[0].level, None)


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


def _percentages(text: str) -> list[int]:
    return sorted(int(number) for number in _PERCENTAGE.findall(text))


def _digits(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())
