#!/usr/bin/env python3
"""Install a character portrait from any local image file.

This is the fallback for when the unpacked client is not available. It takes whatever image you have
- a screenshot of the character screen, or art from a community site - crops and resizes it to the
size the app expects, and writes it under the right filename so it just shows up.

Prefer `scripts/extract_portraits.py`, which copies the real assets out of a client unpacked with
Chaos-Zero-Nightmare-ASSet-Ripper.

Usage:
    python scripts/install_portrait.py <res_id> <face image> [--tp-skill <image>] [--force]

Example:
    python scripts/install_portrait.py 30113 ~/Downloads/hilde.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = REPO_ROOT / "api" / "assets" / "game"

# Sizes taken from the assets already in the repo, which all agree.
FACE = ("faces", "bookmark_face_character_map_{res_id}.png", (72, 72))
TP_SKILL = ("tp_skill", "battle_icon_tp_skill_{res_id}.png", (108, 76))


def _fit(image, size: tuple[int, int]):
    """
    Centre-crop to the target aspect ratio, then resize.

    Plain resizing squashes a portrait that is not already the right shape, which looks obviously
    wrong next to the real assets.

    Args:
        image: A PIL image.
        size: Target (width, height).

    Returns:
        A new RGBA image of exactly `size`.
    """
    from PIL import Image

    target_w, target_h = size
    src_w, src_h = image.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        crop_w = int(src_h * target_ratio)
        left = (src_w - crop_w) // 2
        box = (left, 0, left + crop_w, src_h)
    else:
        crop_h = int(src_w / target_ratio)
        top = (src_h - crop_h) // 2
        box = (0, top, src_w, top + crop_h)

    return image.convert("RGBA").crop(box).resize(size, Image.LANCZOS)


def install(res_id: int, source: Path, spec, force: bool) -> Path:
    """
    Write one asset for a res_id.

    Args:
        res_id: Character or partner res_id.
        source: Any image file Pillow can open.
        spec: One of the FACE / TP_SKILL tuples.
        force: Overwrite an existing file.

    Returns:
        The path written.

    Raises:
        FileExistsError: If the destination exists and `force` is False.
        FileNotFoundError: If the source image does not exist.
    """
    from PIL import Image

    if not source.is_file():
        raise FileNotFoundError(f"no such image: {source}")

    subdir, template, size = spec
    dest = ASSET_ROOT / subdir / template.format(res_id=res_id)
    if dest.exists() and not force:
        raise FileExistsError(f"{dest.relative_to(REPO_ROOT)} already exists, pass --force to replace")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        _fit(image, size).save(dest, "PNG")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a character portrait from a local image.")
    parser.add_argument("res_id", type=int, help="character or partner res_id")
    parser.add_argument("face", type=Path, help="image to use for the portrait")
    parser.add_argument("--tp-skill", type=Path, default=None, help="image for the battle skill icon")
    parser.add_argument("--force", action="store_true", help="replace files that already exist")
    args = parser.parse_args()

    try:
        written = [install(args.res_id, args.face, FACE, args.force)]
        if args.tp_skill:
            written.append(install(args.res_id, args.tp_skill, TP_SKILL, args.force))
    except (FileExistsError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    print("\nRun scripts/copy_portraits.py to mirror faces into the Android assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
