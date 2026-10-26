"""Builds api/data/monster_catalog.json from client_db monster definitions.

Sprint 2h1: feeds the Optimizer's Monster Picker dropdown.
Sprint 2h10: refined DEF derivation -- exact stage-tier lookup replaces
the empirical default_powerstep -> red_1..red_10 heuristic.

Walks <CLIENT_DB>/monster(*)@monster.json shards, extracts monster id +
display name + a representative DEF value + has_weak marker.

DEF derivation (Sprint 2h10)
----------------------------
Every monster row id has form `<base>_<NN>` (e.g. `1004019_10`,
`1007021_02`). The trailing `NN` is the monster level / stage tier index.
It exactly matches the `_NN` in `battle.slot{i}_monster_multiple_link`
entries, confirming it's the in-game stage tier id.

The lookup chain is:

    monster_id "<base>_<NN>"
      -> tier_monster_stat[id=int(NN)]
      -> stage_enter_link_mon_stat_id "stat_NN"
      -> mon_stat[stat_NN].stat_def

Then we apply `monster.stat_def_pct / 100` as a per-monster multiplier
(the same way the runtime does on stage-enter).

Suffixes `_00` (1 monster, missing from tier_monster_stat) and unparseable
suffixes fall back to `stat_1` (DEF 47).

Why the heuristic was wrong
---------------------------
- `default_powerstep` is NOT a stat-curve tier. It's a key into
  `powerstep_define` (1257 rows of dmg/hp/cure/shield revise pct).
- `mon_stat` has 200 stat tiers (`stat_1`..`stat_200`), not 10. The
  `red_1..red_10` rows are one color-banded subset, not the canonical
  curve referenced by stages.

Result: the new DEF distribution caps around `stat_99.stat_def=258`
(times stat_def_pct) instead of the heuristic's spurious 643.

has_weak derivation
-------------------
Monsters with `faction_ego` in the elemental-color set
(RED/ORANGE/BLUE/PURPLE/GREEN) are vulnerable to weak-ego damage. Monsters
with `EGO_NONE`/`none`/`EGO_NORMS`/`EGO_INSTINCT` are not.

Display name
------------
Monster rows store `name` as a string id (e.g. `monster@name@1007021_01`).
We resolve it via the English text shard at `<client>/text/en/text.json`.

Usage: python scripts/build_monster_catalog.py [CLIENT_DIR]

CLIENT_DIR is the extracted client folder holding `db/` and `text/`. It defaults
to the configured one (`api.client_db.client_output_dir()`). The datagen
`monster_catalog` target calls `build_catalog()` directly instead.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUTPUT = REPO / "api" / "data" / "monster_catalog.json"

# Elemental-color faction_ego values that map to has_weak=True.
_WEAK_FACTION_EGOS = {"RED", "ORANGE", "BLUE", "PURPLE", "GREEN"}

# Monster id pattern: anything ending with _NN (digits).
_ID_TIER_RE = re.compile(r"_(\d+)$")


def _load_name_table(client_root: Path) -> dict[str, str]:
    """Return id -> text mapping for monster@name@* keys."""
    text_en = client_root / "text" / "en" / "text.json"
    if not text_en.exists():
        print(f"WARNING: {text_en} not found; falling back to raw name ids",
              file=sys.stderr)
        return {}
    rows = json.loads(text_en.read_text(encoding="utf-8"))
    return {
        r["id"]: r["text"]
        for r in rows
        if isinstance(r, dict) and str(r.get("id", "")).startswith("monster@name@")
    }


def _load_tier_to_mon_stat_key(client_db: Path) -> dict[int, str]:
    """Return tier_id (int from tier_monster_stat.id) -> stage_enter_link_mon_stat_id."""
    p = client_db / "tier_monster_stat@tier_monster_stat.json"
    if not p.exists():
        raise FileNotFoundError(f"Required client_db file missing: {p}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id", ""))
        if not rid.isdigit():
            continue
        msid = str(r.get("stage_enter_link_mon_stat_id", "") or "")
        if msid:
            out[int(rid)] = msid
    return out


def _load_mon_stat_def(client_db: Path) -> dict[str, tuple[int, float]]:
    """Return mon_stat row id -> (stat_def, dmg_decrease_rate).

    We index all rows (not just stat_*), so any string from
    tier_monster_stat.stage_enter_link_mon_stat_id resolves. This includes
    edge keys like 'tutorial', 'stat_1'..'stat_200', etc.
    """
    p = client_db / "mon_stat@mon_stat.json"
    if not p.exists():
        raise FileNotFoundError(f"Required client_db file missing: {p}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, tuple[int, float]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id", ""))
        if not rid:
            continue
        try:
            out[rid] = (int(float(r.get("stat_def", 0) or 0)), float(r.get("dmg_decrease_rate", 0) or 0))
        except (TypeError, ValueError):
            continue
    return out


def _id_to_tier(mid: str) -> int:
    """Parse the trailing `_NN` of a monster id; return 1 on parse failure
    or `_00`.

    Examples:
        "1004019_10" -> 10
        "1007021_02" -> 2
        "1004006_80" -> 80
        "weird_id"   -> 1 (fallback)
        "1234_00"    -> 1 (fallback; _00 not in tier_monster_stat)
    """
    m = _ID_TIER_RE.search(mid)
    if not m:
        return 1
    n = int(m.group(1))
    return n if n >= 1 else 1


def build_catalog(client_root: Path) -> tuple[list[dict], dict[str, int]]:
    """Build the catalog from one extracted client, without writing it.

    Args:
        client_root: The extracted client folder, holding `db/` and `text/`.

    Returns:
        The entries sorted by DEF then name, and counters for the rows that
        were skipped or fell back to the default tier.

    Raises:
        FileNotFoundError: If tier_monster_stat or mon_stat is missing.
        ValueError: If either of them loads empty.
    """
    client_root = Path(client_root)
    client_db = client_root / "db"
    name_table = _load_name_table(client_root)
    tier_to_mskey = _load_tier_to_mon_stat_key(client_db)
    mon_stat_def = _load_mon_stat_def(client_db)
    if not tier_to_mskey or not mon_stat_def:
        raise ValueError("failed to load tier_monster_stat or mon_stat")

    # Fallback DEF for monsters whose tier suffix isn't in tier_monster_stat.
    fallback_msid = tier_to_mskey.get(1, "stat_1")
    fallback_stats = mon_stat_def.get(fallback_msid, (47, 0.0))

    catalog: list[dict] = []
    skipped_no_id = 0
    skipped_dup = 0
    seen_ids: set[str] = set()
    tier_miss = 0

    for shard in sorted(client_db.glob("monster(*)@monster.json")):
        if shard.stat().st_size <= 2:
            continue
        try:
            data = json.loads(shard.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skip {shard.name}: {e}", file=sys.stderr)
            continue
        rows = data if isinstance(data, list) else list(data.values())
        for row in rows:
            if not isinstance(row, dict):
                continue
            mid = row.get("id")
            if not mid:
                skipped_no_id += 1
                continue
            mid = str(mid)
            if mid in seen_ids:
                skipped_dup += 1
                continue
            seen_ids.add(mid)

            name_key = str(row.get("name", "") or "")
            name = name_table.get(name_key) or name_key or mid

            try:
                pct = float(row.get("stat_def_pct", 100) or 100)
            except (TypeError, ValueError):
                pct = 100.0

            tier = _id_to_tier(mid)
            msid = tier_to_mskey.get(tier)
            if msid is None:
                tier_miss += 1
                base_def, dmg_decrease = fallback_stats
            else:
                base_def, dmg_decrease = mon_stat_def.get(msid, fallback_stats)
            def_value = int(round(base_def * (pct / 100.0)))

            faction = str(row.get("faction_ego", "") or "").upper()
            has_weak = faction in _WEAK_FACTION_EGOS

            # Filter out non-combat props (interactive set pieces, half-death
            # markers, etc.) -- they aren't meaningful monsters to optimize
            # against.
            grade = str(row.get("grade", "") or "")
            if grade in (
                "GRADE_INTERACTIVE_PROP",
                "GRADE_PROP_KEEP_HALF_DEATH",
                "GRADE_PROP_KEEP_HALF_DEATH_NOTICE",
            ):
                continue

            catalog.append({
                "id": mid,
                "name": name,
                "def": def_value,
                # The stat row's rate as-is: stat_def_pct scales DEF but not the damage decrease
                "dmg_decrease": dmg_decrease,
                "has_weak": has_weak,
            })

    # Sort by DEF then name for predictable UI order
    catalog.sort(key=lambda e: (e["def"], e["name"]))
    return catalog, {"skipped_no_id": skipped_no_id, "skipped_dup": skipped_dup, "tier_miss": tier_miss}


def main(argv: list[str]) -> int:
    from api.client_db import client_output_dir

    client_root = Path(argv[0]) if argv else client_output_dir()
    try:
        catalog, counts = build_catalog(client_root)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if catalog:
        defs = [e["def"] for e in catalog]
        print(
            f"Wrote {len(catalog)} monsters to {OUTPUT.name} "
            f"(DEF range {min(defs)}-{max(defs)}, "
            f"mean={sum(defs)/len(defs):.0f}). "
            f"skipped_no_id={counts['skipped_no_id']} skipped_dup={counts['skipped_dup']} "
            f"tier_miss={counts['tier_miss']}"
        )
    else:
        print("WARNING: catalog is empty")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
