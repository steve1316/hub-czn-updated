"""Add a combatant or partner the game client has and the app does not.

One command for what `docs/adding-a-character.md` describes by hand: work out what is new, pull the
entry out of the unpacked client, write it into the game data tables, and copy the art across.

Usage:
    python scripts/add_character.py [<output_dir>] [<res_id> ...]
                                    [--dry-run] [--force] [--node-50 <stat>] [--node-60 <stat>]

Examples:
    python scripts/add_character.py                       # everything new, client from CZN_CLIENT_DB
    python scripts/add_character.py 30117 30118           # just these two
    python scripts/add_character.py --dry-run             # show what would be written, write nothing
    python scripts/add_character.py 30117 --node-50 CRate --node-60 CDmg

With no res_ids it takes every combatant and partner the client has, the repo does not, and that has
an English name. That last gate matters: ids appear in the client long before release with no name
yet, so without it a datamined character lands in the app called `char_base@name@30117`.

Nothing here invents data. Where the client is missing rows the script says so and leaves the field
empty rather than guessing, and `--node-50` / `--node-60` are there for the one thing that regularly
has to be read in game instead.
"""
from __future__ import annotations

import argparse
import ast
import codecs
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import extract_combatant  # noqa: E402
import extract_partner  # noqa: E402
import extract_portraits  # noqa: E402
from api.client_db import client_output_dir, table, table_by_id, text_index  # noqa: E402
from entry_format import format_entry  # noqa: E402

CHARACTERS_PY = REPO_ROOT / "api" / "game_data" / "characters.py"
PARTNERS_PY = REPO_ROOT / "api" / "game_data" / "partners.py"
CHAR_BASE_L1_JSON = REPO_ROOT / "api" / "data" / "char_base_l1.json"
ANDROID_ASSETS = REPO_ROOT / "android-app" / "app" / "src" / "main" / "assets"

# The art folders both the desktop app and the Android companion serve portraits from, taken from
# extract_portraits so that adding a pattern there does not silently stop it reaching Android.
ASSET_SUBDIRS = tuple(dict.fromkeys(pattern[2] for pattern in extract_portraits.PATTERNS))

COMBATANT_TABLE = extract_combatant.BASE_TABLE
PARTNER_TABLE = extract_partner.PARTNER_BASE_TABLE

# char_base_l1 field -> the client column it comes from and the type it is stored as.
LEVEL_ONE_FIELDS = (
    ("atk", "s_atk", int),
    ("def", "s_def", int),
    ("hp", "s_hp", int),
    ("cri", "s_cri", float),
    ("cri_dmg", "s_cri_dmg_rate", float),
    ("weak_ego_dmg_rate", "s_weak_ego_dmg_rate", float),
    ("level_group", "link_combatant_level_group", str),
    ("ascend_group", "link_combatant_ascend_group", str),
    ("limit_break_group", "link_combatant_limit_break_group", str),
    ("friendship_group", "link_combatant_friendship_bonus_group", str),
)

# Partners on this ascend group gain HP only, which `get_partner_ascend_bonus` keys off a set.
SSSR_ASCEND_GROUP = "dev_ascend_sssr"

_NAME_PREFIX = "char_base@name@"
_NAME_KEY = re.compile(rf"^{_NAME_PREFIX}(\d+)$")


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Reading the client


def known_res_ids() -> set[int]:
    """
    Every combatant and partner the app already has an entry for.

    Returns:
        The res_ids, ignoring the empty placeholders both tables carry.
    """
    from api.game_data.characters import CHARACTERS
    from api.game_data.partners import PARTNERS

    return {rid for rid, entry in CHARACTERS.items() if entry} | {rid for rid, entry in PARTNERS.items() if entry}


def released_names(output_dir: Path) -> dict[int, str]:
    """
    Every character and partner the client has an English display name for.

    Args:
        output_dir: Root of the unpacked client.

    Returns:
        res_id -> display name. An id with no entry here is in the client but not released yet.
    """
    names: dict[int, str] = {}
    for key, value in text_index(output_dir).items():
        # The catalogue has six figures of keys and only a few hundred are names, so check the cheap
        # prefix before running the regex.
        if not value or not key.startswith(_NAME_PREFIX):
            continue
        match = _NAME_KEY.match(key)
        if match:
            names[int(match.group(1))] = value
    return names


def classify(db: Path, res_id: int) -> str:
    """
    Whether a res_id is a combatant or a partner.

    Args:
        db: The client's `db` folder.
        res_id: The id to look up.

    Returns:
        Either "combatant" or "partner".

    Raises:
        KeyError: If the client has the id in neither table.
    """
    root = db.parent
    if str(res_id) in table_by_id(PARTNER_TABLE, root):
        return "partner"
    row = table_by_id(COMBATANT_TABLE, root).get(str(res_id))
    if row is not None and row.get("char_type") == "CHAR_COMBATANT":
        return "combatant"
    raise KeyError(f"res_id {res_id} is neither a combatant nor a partner in the client")


def level_one_row(db: Path, res_id: int) -> dict:
    """
    A combatant's `char_base_l1.json` row: the level 1 stats and the groups its growth comes from.

    Args:
        db: The client's `db` folder.
        res_id: Combatant res_id.

    Returns:
        The row, with keys in the order the file already uses.

    Raises:
        KeyError: If the combatant has no stat row in the client.
    """
    row = table_by_id(extract_combatant.COMBATANT_TABLE, db.parent).get(str(res_id))
    if row is None:
        raise KeyError(f"res_id {res_id} not found in {extract_combatant.COMBATANT_TABLE}")
    return {field: cast(row[column]) for field, column, cast in LEVEL_ONE_FIELDS}


def find_new(output_dir: Path) -> list[tuple[int, str]]:
    """
    Everything the client has, the repo does not, and that has been released.

    Only playable combatants count. The client's roster is more than twice the app's, because it also
    holds every story NPC with a full stat block - Milia and Karl among them - and `char_use_playable`
    is what separates the two.

    Args:
        output_dir: Root of the unpacked client.

    Returns:
        (res_id, kind) pairs sorted by id, kind being "combatant" or "partner".
    """
    known = known_res_ids()
    names = released_names(output_dir)

    found = []
    for row in table(COMBATANT_TABLE, output_dir):
        res_id = int(row["id"])
        if res_id not in known and res_id in names and row.get("char_type") == "CHAR_COMBATANT" and row.get("char_use_playable") == "YES":
            found.append((res_id, "combatant"))
    for row in table(PARTNER_TABLE, output_dir):
        res_id = int(row["id"])
        if res_id not in known and res_id in names:
            found.append((res_id, "partner"))
    return sorted(found)


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Editing the game data tables


def _read_source(path: Path) -> tuple[str, dict]:
    """
    A file's text with newlines normalised, plus what is needed to write it back unchanged.

    These files are UTF-8 with a BOM and CRLF line endings. Losing either on write turns a one line
    addition into a diff against the whole file.

    Args:
        path: The file to read.

    Returns:
        The text with LF newlines, and the byte order mark and newline style it actually uses.
    """
    raw = path.read_bytes()
    bom = raw.startswith(codecs.BOM_UTF8)
    if bom:
        raw = raw[len(codecs.BOM_UTF8):]
    text = raw.decode("utf-8")
    return text.replace("\r\n", "\n"), {"bom": bom, "newline": "\r\n" if "\r\n" in text else "\n"}


def _write_source(path: Path, source: str, style: dict) -> None:
    """Write text back in the byte order mark and newline style it was read in."""
    path.write_bytes((codecs.BOM_UTF8 if style["bom"] else b"") + source.replace("\n", style["newline"]).encode("utf-8"))


def closing_brace_offset(source: str, table_name: str) -> int:
    """
    Where a module level dict or set literal's closing brace sits.

    Python parses the file, rather than a regex matching an assumed layout. That means no anchor to
    keep in step with how the tables happen to be formatted, and an exact answer for any formatting.

    Args:
        source: The whole file, with LF newlines.
        table_name: The name the literal is assigned to.

    Returns:
        The offset of the closing brace.

    Raises:
        KeyError: If nothing at module level assigns a dict or set literal to that name.
    """
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if not any(isinstance(t, ast.Name) and t.id == table_name for t in targets):
            continue
        if not isinstance(node.value, (ast.Dict, ast.Set)):
            raise KeyError(f"{table_name} is not a dict or set literal")
        lines = source.split("\n")
        return sum(len(line) + 1 for line in lines[:node.value.end_lineno - 1]) + node.value.end_col_offset - 1
    raise KeyError(f"no table named {table_name}")


def insert_into_table(source: str, table_name: str, block: str) -> str:
    """
    Put a block of source in as the last entry of a table.

    Appending rather than sorting is deliberate. None of these tables are in id order, so an entry at
    the end is the only placement that reads as a pure addition in the diff.

    Args:
        source: The whole file, with LF newlines.
        table_name: The table to add to.
        block: The entry source, indented, with no trailing newline.

    Returns:
        The file with the block added.

    Raises:
        KeyError: If there is no such table.
    """
    close = closing_brace_offset(source, table_name)
    return source[:close] + block + "\n" + source[close:]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Writing an entry


def _guard_already_present(res_id: int, force: bool) -> None:
    """
    Stop before writing a res_id the app already has.

    Asking the imported tables rather than grepping the source keeps this from tripping over a number
    that merely happens to appear inside some other entry's values.

    Args:
        res_id: The id about to be written.
        force: Skip the check.

    Raises:
        SystemExit: If the id is already known and `force` is not set.
    """
    if not force and res_id in known_res_ids():
        raise SystemExit(f"{res_id} is already in the game data tables - pass --force to add it again")


def add_combatant(output_dir: Path, res_id: int, nodes: dict[str, str], dry_run: bool, force: bool) -> list[str]:
    """
    Write one combatant into `characters.py` and `char_base_l1.json`.

    Args:
        output_dir: Root of the unpacked client.
        res_id: Combatant res_id.
        nodes: Overrides for `node_50` / `node_60`, for when the client has no effect rows yet.
        dry_run: Print the entry instead of writing it.
        force: Write even when the tables already mention the id.

    Returns:
        Warnings about anything the client could not fill in.
    """
    entry, unfilled = extract_combatant.extract(output_dir, res_id)
    overrides = {key: value for key, value in nodes.items() if value}
    entry.update(overrides)
    unfilled = [key for key in unfilled if key not in overrides]
    block = format_entry(res_id, entry, extract_combatant.ENTRY_KEYS, f"TODO: confirm {', '.join(unfilled)}" if unfilled else "")
    row = level_one_row(output_dir / "db", res_id)

    print(block)
    warnings = []
    if unfilled:
        warnings.append(f"{res_id} {entry['name']}: the client's potential node effects are missing, so {', '.join(unfilled)} "
                        f"came from the weaker tree layout or not at all - confirm in game, or pass --node-50 / --node-60")

    if dry_run:
        return warnings

    _guard_already_present(res_id, force)
    source, style = _read_source(CHARACTERS_PY)
    _write_source(CHARACTERS_PY, insert_into_table(source, "CHARACTERS", block), style)

    text, level_one_style = _read_source(CHAR_BASE_L1_JSON)
    level_one = json.loads(text)
    level_one[str(res_id)] = row
    _write_source(CHAR_BASE_L1_JSON, json.dumps(level_one, indent=2, ensure_ascii=False) + "\n", level_one_style)
    return warnings


def add_partner(output_dir: Path, res_id: int, dry_run: bool, force: bool) -> list[str]:
    """
    Write one partner into `partners.py`, along with its flat stat additions and ascend group.

    Args:
        output_dir: Root of the unpacked client.
        res_id: Partner res_id.
        dry_run: Print the entry instead of writing it.
        force: Write even when the table already mentions the id.

    Returns:
        Warnings about anything the client could not fill in.
    """
    entry, unfilled = extract_partner.extract(output_dir, res_id)
    block = format_entry(res_id, entry, extract_partner.ENTRY_KEYS, f"TODO: review {', '.join(unfilled)}" if unfilled else "")
    detail = extract_partner.partner_row(output_dir / "db", res_id)

    print(block)
    warnings = []
    if unfilled:
        warnings.append(f"{res_id} {entry['name']}: the client could not fill in {', '.join(unfilled)}")
    if detail is None:
        warnings.append(f"{res_id} {entry['name']}: no row in {extract_partner.PARTNER_DETAIL_TABLE}, so its flat stat additions and ascend group were left out")

    if dry_run:
        return warnings

    _guard_already_present(res_id, force)
    source, style = _read_source(PARTNERS_PY)
    source = insert_into_table(source, "PARTNERS", block)

    if detail is not None:
        add = {key: int(detail[f"default_{key}_add"]) for key in ("atk", "def", "hp")}
        source = insert_into_table(source, "PARTNER_DEFAULT_ADD", f'    {res_id}: {{"atk": {add["atk"]}, "def": {add["def"]}, "hp": {add["hp"]}}},')
        if detail.get("link_partner_ascend_group") == SSSR_ASCEND_GROUP:
            source = insert_into_table(source, "SSSR_ASCEND_PARTNERS", f"    {res_id},")

    _write_source(PARTNERS_PY, source, style)
    return warnings


def sync_assets(output_dir: Path, res_ids: list[int]) -> list[str]:
    """
    Copy the art for the new ids out of the client and mirror it into the Android assets.

    Only the ids just added are mirrored. `scripts/copy_portraits.py` mirrors the whole folder, and
    the two sides have drifted apart, so running it here would sweep unrelated files into the diff.

    Args:
        output_dir: Root of the unpacked client.
        res_ids: Everything just added.

    Returns:
        Warnings for any required art the client did not have.
    """
    warnings = []
    for res_id in res_ids:
        copied, missing = extract_portraits.copy_for(res_id, output_dir)
        mirrored = 0
        for subdir in ASSET_SUBDIRS:
            target = ANDROID_ASSETS / subdir
            if not target.is_dir():
                continue
            for source in sorted((extract_portraits.DST_BASE / subdir).glob(f"*_{res_id}*.png")):
                shutil.copy2(source, target / source.name)
                mirrored += 1
        print(f"  {res_id}: copied {copied} art files, mirrored {mirrored} to Android" + (f", missing {len(missing)}" if missing else ""))
        for path in missing:
            warnings.append(f"{res_id}: no {path} in the client, so the app falls back to a generic icon")
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "extract_characters.py")], check=True)
    return warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("args", nargs="*", help="an optional client folder, then the res_ids to add")
    parser.add_argument("--dry-run", action="store_true", help="show what would be written, write nothing")
    parser.add_argument("--force", action="store_true", help="add an id the tables already mention")
    parser.add_argument("--node-50", help="stat for the level 50 potential node, when the client has none")
    parser.add_argument("--node-60", help="stat for the level 60 potential node, when the client has none")
    opts = parser.parse_args(argv[1:])

    from api.client_db import client_output_dir

    rest = opts.args
    if rest and not rest[0].isdigit():
        output_dir, rest = Path(rest[0]), rest[1:]
    else:
        output_dir = client_output_dir()
    if not (output_dir / "db").is_dir():
        print(f"no client db under {output_dir}", file=sys.stderr)
        print("Unpack the client with Chaos-Zero-Nightmare-ASSet-Ripper and set CZN_CLIENT_DB to it.", file=sys.stderr)
        return 2
    if not (output_dir / "text" / "en" / "text.json").is_file():
        print(f"no text/en/text.json under {output_dir} - names cannot be resolved without it", file=sys.stderr)
        return 2

    db = output_dir / "db"
    if rest:
        targets = [(int(raw), classify(db, int(raw))) for raw in rest]
    else:
        targets = find_new(output_dir)
        if not targets:
            print("nothing new in the client")
            return 0
    if (opts.node_50 or opts.node_60) and len(targets) != 1:
        print("--node-50 / --node-60 apply to one res_id, so name exactly one", file=sys.stderr)
        return 2

    nodes = {"node_50": opts.node_50, "node_60": opts.node_60}
    warnings = []
    for res_id, kind in targets:
        print(f"\n{kind} {res_id}:")
        if kind == "combatant":
            warnings += add_combatant(output_dir, res_id, nodes, opts.dry_run, opts.force)
        else:
            warnings += add_partner(output_dir, res_id, opts.dry_run, opts.force)

    if not opts.dry_run:
        print("\nart:")
        warnings += sync_assets(output_dir, [res_id for res_id, _ in targets])

    if warnings:
        print("\nneeds attention:", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)
    print("\nNow run: pytest tests/api/test_character_data.py" + ("" if opts.dry_run else " and review the diff"))
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
