"""Tests for scripts/add_character.py.

The source-editing helpers are pure and run everywhere. Reading the client is gated on the unpacked
data being present, like the other script tests.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import add_character  # noqa: E402

from api.client_db import client_output_dir, have_client_db, have_client_text  # noqa: E402

OUTPUT_DIR = client_output_dir()

needs_client = pytest.mark.skipif(
    not (have_client_db() and have_client_text()),
    reason="game client DB or its text catalogue not available",
)

SAMPLE = '''"""Doc."""

CHARACTERS = {
    1003: {
        "name": "Nia",
    },
}

OTHER = {
    1: 2,
}
'''


def _literal(source: str, table: str):
    """
    The value a module level table is assigned, parsed out of the source.

    Args:
        source: The whole file.
        table: The name the literal is assigned to.

    Returns:
        The dict or set itself. Parsing rather than string matching proves both that the file still
        reads as Python and that an entry really is a key of the table it was aimed at.

    Raises:
        KeyError: If nothing at module level assigns to that name.
    """
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(getattr(target, "id", None) == table for target in targets):
            return ast.literal_eval(node.value)
    raise KeyError(table)


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Editing the game data tables


def test_insert_into_table_lands_before_the_closing_brace():
    out = add_character.insert_into_table(SAMPLE, "CHARACTERS", '    30117: {\n        "name": "Olga",\n    },')
    assert '        "name": "Olga",\n    },\n}\n\nOTHER = {' in out
    assert _literal(out, "CHARACTERS") == {1003: {"name": "Nia"}, 30117: {"name": "Olga"}}
    assert _literal(out, "OTHER") == {1: 2}


def test_insert_into_table_handles_an_annotated_declaration():
    source = "PARTNER_DEFAULT_ADD: dict[int, dict] = {\n    20001: {},\n}\n"
    out = add_character.insert_into_table(source, "PARTNER_DEFAULT_ADD", "    30118: {},")
    assert out == "PARTNER_DEFAULT_ADD: dict[int, dict] = {\n    20001: {},\n    30118: {},\n}\n"


def test_insert_into_table_handles_a_set_literal():
    source = "SSSR = {\n    1025, 20002,\n    30044,\n}\n"
    out = add_character.insert_into_table(source, "SSSR", "    30118,")
    assert _literal(out, "SSSR") == {1025, 20002, 30044, 30118}


def test_insert_into_table_rejects_an_unknown_table():
    with pytest.raises(KeyError):
        add_character.insert_into_table(SAMPLE, "NOPE", "    1: 2,")


def test_insert_into_table_rejects_a_name_that_is_not_a_literal():
    # Writing into something that only looks like a table would produce source that does not parse.
    with pytest.raises(KeyError):
        add_character.insert_into_table("CHARACTERS = dict()\n", "CHARACTERS", "    1: 2,")


@pytest.mark.parametrize("path,table,res_id", [
    (add_character.CHARACTERS_PY, "CHARACTERS", 30115),          # Arabella
    (add_character.PARTNERS_PY, "PARTNERS", 30116),              # Licinia
    (add_character.PARTNERS_PY, "PARTNER_DEFAULT_ADD", 20001),
    (add_character.PARTNERS_PY, "SSSR_ASCEND_PARTNERS", 1025),
])
def test_every_real_table_a_write_targets_is_reachable(path, table, res_id):
    # A rename of any of these has to fail loudly here rather than quietly stop the script writing.
    source, _ = add_character._read_source(path)
    add_character.closing_brace_offset(source, table)
    assert res_id in _literal(source, table)


@pytest.mark.parametrize("path", [add_character.CHARACTERS_PY, add_character.PARTNERS_PY, add_character.CHAR_BASE_L1_JSON])
def test_writing_a_file_back_unchanged_is_byte_identical(path, tmp_path):
    # These files are UTF-8 with a BOM and CRLF line endings. Losing either on write would turn a one
    # line addition into a diff against every line of the file.
    source, style = add_character._read_source(path)
    copy = tmp_path / path.name
    add_character._write_source(copy, source, style)
    assert copy.read_bytes() == path.read_bytes()


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Against the real client


@needs_client
def test_released_names_resolve_to_real_text():
    names = add_character.released_names(OUTPUT_DIR)
    assert names, "no English names resolved at all"
    assert all(not name.startswith("char_base@") for name in names.values())


@needs_client
def test_known_combatants_and_partners_are_classified_correctly():
    db = OUTPUT_DIR / "db"
    assert add_character.classify(db, 30115) == "combatant"   # Arabella
    assert add_character.classify(db, 30116) == "partner"     # Licinia
    with pytest.raises(KeyError):
        add_character.classify(db, 1)


@needs_client
def test_level_one_rows_match_what_the_repo_already_has():
    # char_base_l1.json feeds the growth curve, so a wrong row silently shifts every stat downstream.
    existing = json.loads((REPO_ROOT / "api" / "data" / "char_base_l1.json").read_text(encoding="utf-8"))
    wrong = []
    for res_id, row in existing.items():
        try:
            derived = add_character.level_one_row(OUTPUT_DIR / "db", int(res_id))
        except KeyError:
            continue
        if derived != row:
            wrong.append((res_id, derived, row))
    assert not wrong, f"derived level 1 rows disagree with the repo: {wrong}"


@needs_client
def test_nothing_already_in_the_repo_is_reported_as_new():
    known = add_character.known_res_ids()
    for res_id, _kind in add_character.find_new(OUTPUT_DIR):
        assert res_id not in known, f"{res_id} is already in the repo"


@needs_client
def test_story_npcs_are_not_reported_as_new():
    # The client's roster is more than twice the app's because it holds every story NPC with a full
    # stat block. Milia and Karl have English names and real stats, so only the playable flag keeps
    # them out - without it a run would add forty characters nobody can use.
    found = {res_id for res_id, _kind in add_character.find_new(OUTPUT_DIR)}
    assert not found & {1007, 1012, 1015, 1020}, "story NPCs leaked into the new list"
