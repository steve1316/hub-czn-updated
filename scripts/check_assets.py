#!/usr/bin/env python3
"""Report which characters and partners are missing image assets.

A newly added character shows a blank silhouette until its art is in the repo, which is easy to miss.
This says exactly what is absent so the gap is visible.

Usage:
    python scripts/check_assets.py            # report
    python scripts/check_assets.py --strict   # exit 1 if a required asset is missing
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "api"))

ASSET_ROOT = REPO_ROOT / "api" / "assets" / "game"

# (subdir, filename template, required). Mirrors PATTERNS in extract_portraits.py.
ASSETS = [
    ("faces", "bookmark_face_character_map_{res_id}.png", True),
    ("tp_skill", "battle_icon_tp_skill_{res_id}.png", True),
]


def everyone() -> dict[int, str]:
    """
    Every combatant and partner we know about.

    Returns:
        res_id -> display name.
    """
    from game_data.characters import CHARACTERS
    from game_data.partners import PARTNERS
    out = {r: c["name"] for r, c in CHARACTERS.items() if c}
    out.update({r: p["name"] for r, p in PARTNERS.items() if p})
    return out


def missing_for(res_id: int) -> list[str]:
    """
    Which required asset files are absent for one res_id.

    Args:
        res_id: Character or partner res_id.

    Returns:
        Names of the missing subdirs, e.g. ["faces"].
    """
    gaps = []
    for subdir, template, required in ASSETS:
        if not required:
            continue
        if not (ASSET_ROOT / subdir / template.format(res_id=res_id)).exists():
            gaps.append(subdir)
    return gaps


def main() -> int:
    people = everyone()
    rows = [(rid, name, gaps) for rid, name in sorted(people.items()) if (gaps := missing_for(rid))]

    if not rows:
        print(f"All {len(people)} characters and partners have their required assets.")
        return 0

    print(f"{len(rows)} of {len(people)} entries are missing required assets:\n")
    print(f"  {'res_id':>7}  {'name':14} missing")
    for rid, name, gaps in rows:
        print(f"  {rid:>7}  {name:14} {', '.join(gaps)}")
    print("\nWith the client unpacked: python scripts/extract_portraits.py <res_id> [<res_id> ...]")
    print("Without it:                python scripts/install_portrait.py <res_id> <image> [--tp-skill <image>]")
    return 1 if "--strict" in sys.argv else 0


if __name__ == "__main__":
    raise SystemExit(main())
