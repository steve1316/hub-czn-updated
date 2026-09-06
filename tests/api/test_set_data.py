"""
Shape and freshness checks for the Memory Fragment set table.

These run over every entry rather than naming individual sets, so a newly added set is covered the
moment it lands. The capture check is the one that matters most: `SETS` is typed by hand with no
extractor behind it. With a client unpack present the checks at the bottom compare it against the
game's own files, which is the real freshness signal. Without one, the capture scan is the fallback:
it notices a new set only once you own a fragment from it.
"""

import json
from functools import lru_cache
from pathlib import Path

import pytest

from api.capture.constants import OUTPUT_DIR
from api.client_db import client_output_dir, have_client_db, have_client_text
from api.game_data.sets import FOUR_PIECE_SETS, SETS, TWO_PIECE_SETS
from scripts.export_sets_json import android_sets
from scripts.extract_sets import STAT_LINKS, extract_sets

REPO = Path(__file__).resolve().parents[2]
ANDROID_SETS = REPO / "android-app" / "app" / "src" / "main" / "assets" / "sets.json"

# The stats the optimizer can actually apply, from the branch in GearOptimizer.calculate_build_stats.
# A set bonus naming anything else would score as nothing. extract_sets maps the client's ids onto
# this same vocabulary, so take it from there rather than keeping a third copy.
STAT_NAMES = set(STAT_LINKS.values())

# Sets seen in a real capture that SETS cannot name yet, because their names and bonuses need a game
# client unpack. Listing one here keeps the capture check live for *other* new sets instead of
# switching it off wholesale. test_known_missing_sets_are_still_missing fails once one is added.
KNOWN_MISSING_SETS: set[int] = set()

# Sets the client defines but no piece links to, so no player can own them. extract_sets skips these,
# and the client check below allows SETS to keep them.
UNRELEASED_SETS = {21}

SET_ENTRIES = list(SETS.items())
STAT_SETS = [(sid, s) for sid, s in SET_ENTRIES if s["type"] == "stat"]
TWO_PIECE_BONUS_SETS = [(sid, s) for sid, s in SET_ENTRIES if s.get("two_piece")]


def _capture_with_res_ids(tmp_path, res_ids):
    """
    Write a minimal capture file holding one fragment per given res_id.

    Only `id` and `res_id` are set, since those are the two fields MemoryFragment.from_json needs.

    Args:
        tmp_path: pytest tmp_path fixture, the directory to write the capture into.
        res_ids: Piece res_ids to include, which decide the set ids the loader will see.

    Returns:
        Path to the written capture file, as a string ready to hand to load_data.
    """
    pieces = [{"id": i, "res_id": rid} for i, rid in enumerate(res_ids)]
    path = tmp_path / "memory_fragments_test.json"
    path.write_text(json.dumps({"inventory": {"piece_items": pieces}}), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("set_id,info", SET_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_every_set_is_well_formed(set_id, info):
    assert info["name"]
    assert info["pieces"] in (2, 4)
    assert info["type"] in ("stat", "conditional")
    assert info["bonus"]


@pytest.mark.parametrize("set_id,info", STAT_SETS, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_stat_sets_carry_a_scorable_bonus(set_id, info):
    """A "stat" set with no stat or value would score as nothing, the same as an unknown set."""
    assert info["stat"] in STAT_NAMES
    assert isinstance(info["value"], (int, float))
    assert info["value"] > 0


@pytest.mark.parametrize("set_id,info", TWO_PIECE_BONUS_SETS, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_two_piece_sub_bonus_is_scorable(set_id, info):
    """The optimizer reads `two_piece` on four-piece sets, so it needs the same stat and value."""
    two_piece = info["two_piece"]
    assert two_piece["stat"] in STAT_NAMES
    assert two_piece["value"] > 0


def test_derived_lists_cover_every_set():
    """Guards the derivation at the bottom of sets.py, in case it is ever replaced by typed lists."""
    assert set(TWO_PIECE_SETS) | set(FOUR_PIECE_SETS) == set(SETS)
    assert not set(TWO_PIECE_SETS) & set(FOUR_PIECE_SETS)


def test_set_names_are_unique():
    """The Android asset is keyed by name, so a duplicate name would silently drop a set."""
    names = [s["name"] for s in SETS.values()]
    assert len(names) == len(set(names))


def test_android_sets_asset_matches_the_table():
    asset = json.loads(ANDROID_SETS.read_text(encoding="utf-8"))
    assert asset == android_sets(), "run python scripts/export_sets_json.py"


def test_known_missing_sets_are_still_missing():
    """Once a set from the pending list is added, stop excusing it in the capture check below."""
    added = sorted(KNOWN_MISSING_SETS & set(SETS))
    assert not added, f"sets {added} are in SETS now - drop them from KNOWN_MISSING_SETS in this file"


def test_every_captured_set_id_is_known():
    """
    Any set the player owns must be in `SETS`, apart from the ones already known to be missing.

    Captures hold the player's own account data so they are gitignored, which means this skips on a
    machine that has never run one. That is the intended tradeoff - the check costs nothing to keep
    and it is the only thing standing between a game update and a silently stale table.
    """
    captures = sorted(OUTPUT_DIR.glob("memory_fragments_*.json"))
    if not captures:
        pytest.skip("no memory fragment capture on this machine")
    capture = captures[-1]

    pieces = json.loads(capture.read_text(encoding="utf-8")).get("inventory", {}).get("piece_items", [])
    assert pieces, f"{capture.name} holds no piece_items"

    # The set id is the last three digits of a fixed 7-digit res_id. This mirrors the decode in
    # MemoryFragment.from_json, so guard the layout rather than let a schema change yield junk ids.
    bad = [p["res_id"] for p in pieces if len(str(p["res_id"])) != 7]
    assert not bad, f"res_id layout changed, expected 7 digits: {bad[:5]}"

    unknown = sorted({int(str(p["res_id"])[4:]) for p in pieces} - set(SETS) - KNOWN_MISSING_SETS)
    assert not unknown, f"{capture.name} holds sets missing from api/game_data/sets.py: {unknown}"


def test_load_data_warns_once_about_unknown_sets(tmp_path, capsys):
    """The warning is a developer breadcrumb on server stdout - the UI shows Unknown(<id>) instead."""
    from api.optimizer.optimizer import GearOptimizer

    # 1114099 and 1124099 are both set 99, which no game update will plausibly reach soon.
    optimizer = GearOptimizer()
    optimizer.load_data(_capture_with_res_ids(tmp_path, [1114099, 1124099, 1114009]))

    out = capsys.readouterr().out
    assert "[99]" in out, f"unknown set 99 was not reported: {out!r}"
    assert out.count("Unknown Memory Fragment set") == 1, f"expected one warning, got: {out!r}"
    assert "api/game_data/sets.py" in out, "warning should say where to add the set"


def test_load_data_is_quiet_when_every_set_is_known(tmp_path, capsys):
    from api.optimizer.optimizer import GearOptimizer

    optimizer = GearOptimizer()
    optimizer.load_data(_capture_with_res_ids(tmp_path, [1114009, 1124011]))

    assert "Unknown Memory Fragment set" not in capsys.readouterr().out


needs_client_db = pytest.mark.skipif(
    not (have_client_db() and have_client_text()), reason="game client DB not available"
)


@lru_cache(maxsize=1)
def client_sets() -> dict:
    """
    The sets the client defines, read once for the whole module.

    Returns:
        The mapping `extract_sets` produces, cached because the parametrized checks below would
        otherwise re-parse the client's 105k-row text catalogue for every set.
    """
    return extract_sets(client_output_dir())


@needs_client_db
def test_every_obtainable_set_in_the_client_is_in_the_table():
    """The check that would have caught sets 28 and 29 in February instead of September."""
    client = client_sets()
    missing = sorted(set(client) - set(SETS))
    assert not missing, f"the client has sets the table does not: {missing}"


@needs_client_db
def test_no_table_entry_is_unknown_to_the_client():
    client = client_sets()
    extra = sorted(set(SETS) - set(client) - UNRELEASED_SETS)
    assert not extra, f"the table has sets the client does not: {extra}"


@needs_client_db
def test_unreleased_sets_are_still_unreleased():
    """The ratchet for UNRELEASED_SETS, so the exemption cannot quietly outlive its reason."""
    released = sorted(UNRELEASED_SETS & set(client_sets()))
    assert not released, f"sets {released} have pieces in the game now - drop them from UNRELEASED_SETS"


@needs_client_db
@pytest.mark.parametrize("set_id,info", SET_ENTRIES, ids=lambda v: v["name"] if isinstance(v, dict) else str(v))
def test_every_entry_matches_the_client(set_id, info):
    """Guards against a bonus the game does not grant, which would inflate every build holding it."""
    client = client_sets()
    if set_id not in client:
        pytest.skip("set has no pieces in the game yet")
    theirs = client[set_id]
    assert info["name"] == theirs["name"]
    assert info["pieces"] == theirs["pieces"]
    assert info["type"] == theirs["type"]
    if theirs["type"] == "stat":
        assert (info["stat"], info["value"]) == (theirs["stat"], theirs["value"])
    assert info.get("two_piece") == theirs.get("two_piece")
