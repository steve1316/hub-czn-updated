"""Copy all portrait/icon assets needed by the optimizer for given res_ids.

The frontend uses four distinct filename patterns under `/assets/game/`, each backed by a different
folder in the unpacked client. Missing any one of them leaves visible empty silhouettes or grey
rectangles.

Needs the client unpacked with Chaos-Zero-Nightmare-ASSet-Ripper. Set `CZN_CLIENT_DB` to the output
folder, or pass it as the first argument. `scripts/install_portrait.py` is the fallback when the
client is not available.

Usage:
    python scripts/extract_portraits.py [<output_dir>] <res_id> [<res_id> ...]

Example:
    python scripts/extract_portraits.py 1055 30095

After running, call `scripts/copy_portraits.py` to mirror the bookmark files into the Android assets
directory.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DST_BASE = REPO_ROOT / "api" / "assets" / "game"

# (source-relative-dir, filename-template, destination-subdir, required)
# `{res_id}` is substituted. Multiple entries with the same dst form variants.
PATTERNS = [
    ("face/character",            "bookmark_face_character_map_{res_id}.png", "faces",    True),
    ("tp_skill",                  "battle_icon_tp_skill_{res_id}.png",        "tp_skill", True),
    ("collapse/collapse_illustration", "collapse_{res_id}_01.png",            "collapse", False),
    ("collapse/collapse_illustration", "collapse_{res_id}_02.png",            "collapse", False),
]


def copy_for(res_id: int, output_dir: Path) -> tuple[int, list[str]]:
    """
    Copy every asset the frontend needs for one res_id.

    Args:
        res_id: Character or partner res_id.
        output_dir: Root of the unpacked client.

    Returns:
        How many files were copied, and the source paths of any required ones that were absent.
    """
    copied = 0
    missing: list[str] = []
    for src_subdir, template, dst_subdir, required in PATTERNS:
        fname = template.format(res_id=res_id)
        src = output_dir / src_subdir / fname
        if not src.exists():
            if required:
                missing.append(f"{src_subdir}/{fname}")
            continue
        dst_dir = DST_BASE / dst_subdir
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst_dir / fname)
        copied += 1
    return copied, missing


def parse_args(argv: list[str]) -> tuple[Path, list[int]]:
    """
    Split the command line into an output dir and the res_ids to copy.

    The output dir is optional. When the first argument is not a number it is taken as the path,
    otherwise the path comes from `CZN_CLIENT_DB`.

    Args:
        argv: Arguments after the script name.

    Returns:
        The client root and the res_ids.

    Raises:
        ValueError: If no res_ids were given, or one is not a number.
    """
    from api.client_db import client_output_dir

    if argv and not argv[0].isdigit():
        output_dir, rest = Path(argv[0]), argv[1:]
    else:
        output_dir, rest = client_output_dir(), argv
    if not rest:
        raise ValueError("no res_ids given")
    return output_dir, [int(raw) for raw in rest]


def main(argv: list[str]) -> int:
    try:
        output_dir, res_ids = parse_args(argv[1:])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Usage: python scripts/extract_portraits.py [<output_dir>] <res_id> [<res_id> ...]",
              file=sys.stderr)
        return 2
    if not output_dir.exists():
        print(f"output_dir not found: {output_dir}", file=sys.stderr)
        print("Unpack the client with Chaos-Zero-Nightmare-ASSet-Ripper and set CZN_CLIENT_DB to it.",
              file=sys.stderr)
        return 2

    overall_missing: list[str] = []
    for res_id in res_ids:
        copied, missing = copy_for(res_id, output_dir)
        print(f"  {res_id}: copied {copied} files" + (f", missing {len(missing)} required" if missing else ""))
        for m in missing:
            print(f"    [MISSING] {m}")
        overall_missing.extend(missing)

    if overall_missing:
        print(f"\nWARNING: {len(overall_missing)} required source file(s) missing - frontend will fall back to empty placeholders for those slots.",
              file=sys.stderr)
        print("Usually `face/` and `tp_skill/` were never exported - they sort late, so an export that "
              "stopped early has neither.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
