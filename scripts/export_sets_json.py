"""Export api/game_data/sets.py::SETS to the Android asset the app reads.

The Android side needs only a name to id map, which is what SetRepository.kt expects from
assets/sets.json. Run this after adding or renaming a set. tests/api/test_set_data.py imports
android_sets() and fails if the checked-in asset has drifted from the table.

Usage:
    python scripts/export_sets_json.py [<out_path>]
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.game_data.sets import SETS

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), '..', 'android-app', 'app', 'src', 'main', 'assets', 'sets.json')


def android_sets() -> dict[str, int]:
    """
    The Android asset's contents, derived from `SETS`.

    Returns:
        A set name to set id mapping, the shape `SetRepository.kt` reads from assets/sets.json.
    """
    return {s["name"]: sid for sid, s in SETS.items()}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(android_sets(), f, indent=2, ensure_ascii=False)
    print(f"Exported {len(android_sets())} sets to {out}")
