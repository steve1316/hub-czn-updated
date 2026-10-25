"""
Card art helpers shared by the targets that add images: encoding a client illustration, and deciding whether to.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from api.client_db import REPO_ROOT
from scripts.datagen.runner import Context


def webp(source: Path, *, quality: int, size: tuple[int, int] | None = None) -> bytes:
    """
    Encode a client illustration as WebP.

    Args:
        source: The client PNG.
        quality: WebP quality.
        size: Resize to this size first, or keep the original size.

    Returns:
        The encoded bytes.
    """
    image = Image.open(source).convert("RGBA")
    if size:
        image = image.resize(size, Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=quality)
    return buffer.getvalue()


def wanted(ctx: Context, path: Path) -> bool:
    """
    Whether an image should be encoded this run.

    Args:
        ctx: The run context.
        path: The repo-relative image path.

    Returns:
        True when the image is missing, or art is being refreshed.
    """
    return ctx.refresh_art or not (REPO_ROOT / path).exists()
