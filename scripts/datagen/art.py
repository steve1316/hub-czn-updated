"""
Card art helpers shared by the targets that add images: encoding a client illustration, and deciding whether to.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import IO

from PIL import Image

from api.client_db import REPO_ROOT
from scripts.datagen.runner import Context

# Client art is kept at its full size, encoded at this WebP quality.
CLIENT_ART_QUALITY = 90


def webp(source: Path | IO[bytes], *, quality: int) -> bytes:
    """
    Encode a client illustration as WebP.

    Args:
        source: The client PNG, or an open picture file.
        quality: WebP quality.

    Returns:
        The encoded bytes.
    """
    image = Image.open(source).convert("RGBA")
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
