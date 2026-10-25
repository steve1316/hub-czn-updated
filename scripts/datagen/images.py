"""
Identify the pictures in the Guides sheet using the game's own art.

Character faces in the sheet are the game's face portraits, so a perceptual hash finds them exactly. Cards are full
in-game card renders with a frame, name and text drawn over the art, so they are matched by sliding the bare client
illustration under the render's art window and keeping the best fit. Only a clear winner counts. Anything ambiguous is
reported rather than guessed.

Pictures those two miss, such as a face cropped differently or another character's card, fall back to `SiftMatcher`,
which matches local features and so survives frames, crops and rescaling. It needs OpenCV, imported only when used.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Generic, TypeVar

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

# SIFT features found per image, Lowe's ratio for a good feature match, and the RANSAC reprojection limit in pixels.
SIFT_FEATURES = 600
SIFT_RATIO = 0.75
SIFT_REPROJECTION = 6.0
# Fewer good feature matches than this cannot fit a transform.
SIFT_MIN_GOOD = 6
# A transform that shrinks or grows the picture more than this is degenerate, such as every point collapsing onto one spot.
SIFT_SCALE_RANGE = (0.25, 4.0)
# Candidates are shrunk to this longest side before their features are found.
SIFT_MAX_SIDE = 512
# The best candidate needs this many inliers, where a wrong one rarely reaches 12. Every candidate within `SIFT_MIN_RATIO`
# of the best is a contender.
SIFT_MIN_INLIERS = 20
SIFT_MIN_RATIO = 2.0
# Contenders are laid over the picture and compared by colour (mean pixel difference, 0-255). The winner must be at most
# this far off, since a card's frame and glow keep even the right art around 10-60, and beat the next contender by the margin.
SIFT_MAX_COLOUR_DIFFERENCE = 64
SIFT_COLOUR_MARGIN = 8
# Sheet pictures are enlarged by this much before matching, since they are small next to the client art.
SIFT_QUERY_SCALE = 2

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


class SiftMatcher(Generic[_Key]):
    """Finds which candidate a picture shows by matching SIFT features, then checking the colours of the closest ones."""

    def __init__(self, candidates: dict[_Key, list[Path]], query_box: tuple[int, int, int, int] | None = None, query_size: tuple[int, int] | None = None):
        """
        Args:
            candidates: Key -> the images that show it. A key scores the best of its images.
            query_box: The part of a resized picture to match, such as a card's art window. The whole picture when None.
            query_size: The size a picture is resized to before matching. Its own size when None.
        """
        import cv2  # Only uncached guide pictures need OpenCV, so it is not a sidecar dependency.
        import numpy

        self._cv2 = cv2
        self._np = numpy
        self._sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
        self._matcher = cv2.BFMatcher()
        self.query_box = query_box
        self.query_size = query_size
        self._candidates: list[tuple[_Key, Path, list, object]] = []
        for key, paths in candidates.items():
            for path in paths:
                art = self._candidate_image(path)
                points, descriptors = self._sift.detectAndCompute(self._grey(art), None)
                if descriptors is not None:
                    self._candidates.append((key, path, points, descriptors))

    def match(self, image: Image.Image) -> _Key | None:
        """
        The candidate a picture shows.

        Args:
            image: The sheet's picture.

        Returns:
            The winning key, or None when no candidate is a clear match.
        """
        query = self._query_image(image)
        points, descriptors = self._sift.detectAndCompute(self._grey(query), None)
        if descriptors is None or len(points) < SIFT_MIN_GOOD:
            return None
        best: dict[_Key, tuple[int, Path, object]] = {}
        for key, path, candidate_points, candidate_descriptors in self._candidates:
            inliers, transform = self._fit(points, descriptors, candidate_points, candidate_descriptors)
            if inliers > best.get(key, (0,))[0]:
                best[key] = (inliers, path, transform)
        ranked = sorted(best.items(), key=lambda item: -item[1][0])
        if not ranked or ranked[0][1][0] < SIFT_MIN_INLIERS:
            return None
        contenders = [item for item in ranked if item[1][0] * SIFT_MIN_RATIO > ranked[0][1][0]]
        # Features can line up the wrong art, and recoloured art (a monster card and its stronger form) shares them, so colour decides.
        differences = {key: self._colour_difference(query, path, transform) for key, (_, path, transform) in contenders}
        return _clear_winner(differences, margin=SIFT_COLOUR_MARGIN, max_distance=SIFT_MAX_COLOUR_DIFFERENCE)

    def _fit(self, points: list, descriptors, candidate_points: list, candidate_descriptors) -> tuple[int, object]:
        """
        How well a picture's features map onto one candidate's.

        Args:
            points: The picture's keypoints.
            descriptors: Their descriptors.
            candidate_points: The candidate's keypoints.
            candidate_descriptors: Their descriptors.

        Returns:
            The number of good matches that agree on one transform, and that picture -> candidate transform. (0, None) when
            there is no plausible transform.
        """
        np = self._np
        pairs = self._matcher.knnMatch(descriptors, candidate_descriptors, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < SIFT_RATIO * pair[1].distance]
        if len(good) < SIFT_MIN_GOOD:
            return 0, None
        source = np.float32([points[match.queryIdx].pt for match in good])
        target = np.float32([candidate_points[match.trainIdx].pt for match in good])
        # RANSAC samples at random, so a fixed seed keeps the result the same from run to run.
        self._cv2.setRNGSeed(0)
        transform, mask = self._cv2.estimateAffinePartial2D(source, target, method=self._cv2.RANSAC, ransacReprojThreshold=SIFT_REPROJECTION)
        smallest, largest = SIFT_SCALE_RANGE
        if transform is None or not smallest <= float(np.hypot(transform[0, 0], transform[1, 0])) <= largest:
            return 0, None
        return int(mask.sum()), transform

    def _colour_difference(self, query: Image.Image, path: Path, transform) -> float:
        """
        The mean pixel difference between a picture and a candidate laid over it.

        Args:
            query: The prepared picture.
            path: The candidate image.
            transform: The picture -> candidate transform from `_fit`.

        Returns:
            The difference (0-255) over the area the candidate covers, or 255 when it covers none.
        """
        np = self._np
        size = query.size
        art = np.asarray(self._candidate_image(path))
        warped = self._cv2.warpAffine(art, transform, size, flags=self._cv2.WARP_INVERSE_MAP)
        covered = self._cv2.warpAffine(np.ones(art.shape[:2], np.uint8), transform, size, flags=self._cv2.WARP_INVERSE_MAP) > 0
        if not covered.any():
            return 255.0
        return float(np.abs(warped.astype(np.int16) - np.asarray(query).astype(np.int16))[covered].mean())

    def _query_image(self, image: Image.Image) -> Image.Image:
        """A sheet picture resized, cropped and enlarged for matching."""
        if self.query_size:
            image = image.resize(self.query_size)
        if self.query_box:
            image = image.crop(self.query_box)
        return image.resize((image.width * SIFT_QUERY_SCALE, image.height * SIFT_QUERY_SCALE), Image.BICUBIC)

    @staticmethod
    def _candidate_image(path: Path) -> Image.Image:
        """A candidate image, flattened and shrunk to at most `SIFT_MAX_SIDE`."""
        art = load(path.read_bytes())
        art.thumbnail((SIFT_MAX_SIDE, SIFT_MAX_SIDE), Image.LANCZOS)
        return art

    def _grey(self, image: Image.Image):
        """An image as the greyscale array OpenCV expects."""
        return self._np.asarray(image.convert("L"))
