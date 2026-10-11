"""
A tiny extracted client written to a temp folder, for tests that must not depend on the real one.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_client(root: Path, tables: dict[str, list[dict]], text: dict[str, str]) -> Path:
    """
    Write shard files and a text catalogue in the client's layout.

    Args:
        root: The folder to write into.
        tables: File name inside `db/` -> its rows.
        text: Text key -> English string.

    Returns:
        `root`, ready to pass to `Client` or `Context`.
    """
    (root / "db").mkdir(parents=True, exist_ok=True)
    (root / "text" / "en").mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        (root / "db" / name).write_text(json.dumps(rows), encoding="utf-8")
    catalogue = [{"id": key, "text": value} for key, value in text.items()]
    (root / "text" / "en" / "text.json").write_text(json.dumps(catalogue), encoding="utf-8")
    return root
