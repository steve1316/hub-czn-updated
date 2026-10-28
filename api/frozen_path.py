from __future__ import annotations

import os
import sys
from pathlib import Path


def add_vribbels_to_path() -> None:
    """Add the api/ directory to sys.path so bare imports (optimizer, models, game_data, capture)
    resolve correctly in both dev mode and PyInstaller frozen mode."""
    if getattr(sys, 'frozen', False):
        target = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        # This file lives in api/; add api/ itself so sibling packages are importable.
        target = os.path.dirname(os.path.abspath(__file__))
    if target not in sys.path:
        sys.path.insert(0, target)


def data_path(filename: str) -> Path:
    """
    Locate a file in `api/data/`, which the spec bundles as `data/`.

    Args:
        filename: The file name inside the data folder.

    Returns:
        Its path in both dev mode and PyInstaller frozen mode.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'data' / filename  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / 'data' / filename
