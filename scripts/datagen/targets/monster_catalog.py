"""
The Optimizer's monster picker: every combat monster with its name, representative DEF and weakness flag.

The derivation (stage tier -> stat curve -> DEF) lives in `scripts/build_monster_catalog.py`. This target runs that same
logic against the configured client instead of the script's own default, and hands the result to the runner.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import build_monster_catalog
from scripts.datagen.client import clean_text
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes

NAME = "monster_catalog"
OFFLINE = True

CATALOG_PATH = Path("api/data/monster_catalog.json")


def build(ctx: Context) -> TargetResult:
    """
    Generate the monster catalog.

    Args:
        ctx: The run context.

    Returns:
        The catalog file, a summary of how it differs from the current one, and a warning when names could not be read.
    """
    catalog, counts = build_monster_catalog.build_catalog(ctx.client.root)
    # The script reads names raw, so give them the same character fixes and tidy pass as all other generated text.
    for entry in catalog:
        entry["name"] = ctx.text(clean_text(entry["name"]), sentences=False)
    catalog.sort(key=lambda entry: (entry["def"], entry["name"]))
    issues = []
    if not ctx.client.has_text():
        issues.append(Issue("warning", f"{NAME}: no text catalogue, so monster names fall back to their text keys"))
    if counts["tier_miss"]:
        issues.append(Issue("warning", f"{NAME}: {counts['tier_miss']} monsters have a tier with no stat row and use the tier 1 DEF"))
    return TargetResult({CATALOG_PATH: json_bytes(catalog)}, summarise(catalog, _current_ids()), issues)


def summarise(catalog: list[dict], current_ids: set[str]) -> str:
    """
    One line comparing the generated catalog with the committed one.

    Args:
        catalog: The generated entries.
        current_ids: The ids in the committed file.

    Returns:
        Such as "610 monsters (+100, -0)".
    """
    ids = {entry["id"] for entry in catalog}
    return f"{len(catalog)} monsters (+{len(ids - current_ids)}, -{len(current_ids - ids)})"


def _current_ids() -> set[str]:
    """The monster ids in the committed catalog, or none when it does not exist yet."""
    path = REPO_ROOT / CATALOG_PATH
    return {entry["id"] for entry in json.loads(path.read_text(encoding="utf-8"))} if path.is_file() else set()
