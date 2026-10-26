"""
Tests for the `glossary` datagen target.

Reading a term's text from the client is checked on a tiny fixture client written to a temp folder. Turning the overrides
file into entries is checked with a fake lookup, so each validation rule can be hit on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.datagen.overrides import Overrides
from scripts.datagen.runner import Context
from scripts.datagen.targets import glossary

TEXT = {
    "tooltip@title@t_cs00_0004": "Agony",
    "tooltip@desc@t_cs00_0004": "At the end of the turn, #result_coeff_ev_0# $Fixed DoT$<br>Max <cc>20</> stacks",
    "tooltip@title@talent_lead": "Lead",
    "tooltip@desc@talent_lead": "#lead_pct# chance to decrease Cost by <cc>1</>",
    "tooltip@title@card_when_break": "Attunement:",
    "tooltip@desc@card_when_break": "When this card is $Draw$n, activate effect",
    "attribute_electric": "Instinct",
    "help_menu@name@help_025": "Ravage",
    "tt_pg@desc@024": "Enemies become <color_orange>Ravaged</>.",
    "tooltip@title@t_cs00_0369": "Fracture",
    "tooltip@desc@t_cs00_0369": "Halve $Fracture$ stacks (max <cc>#tv_max#</> stacks)",
}

TOOLTIPS = [
    {"id": "T_CS00_0004", "title": "tooltip@title@T_CS00_0004", "desc": "tooltip@desc@T_CS00_0004", "desc_battle": "none", "link_cs_id": "cs00_0004"},
    {"id": "TALENT_LEAD", "title": "tooltip@title@TALENT_LEAD", "desc": "none", "desc_outgame": "tooltip@desc@TALENT_LEAD", "link_cs_id": "none"},
    {"id": "T_CS00_0369", "title": "tooltip@title@T_CS00_0369", "desc": "tooltip@desc@T_CS00_0369", "link_cs_id": "cs00_0369"},
]

STATUSES = [
    {"id": "cs00_0004", "link_skill_eff_id": "[cs00_0004_01]"},
    {"id": "cs00_0369", "link_skill_eff_id": "[]", "overlay_value_max": "30"},
]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _context(tmp_path: Path) -> Context:
    """
    A run context over a fixture client.

    Args:
        tmp_path: pytest's temp folder.

    Returns:
        The context.
    """
    db = tmp_path / "db"
    db.mkdir()
    (db / "tooltip@tooltip.json").write_text(json.dumps(TOOLTIPS), encoding="utf-8")
    (db / "cs(card1)@cs.json").write_text(json.dumps(STATUSES), encoding="utf-8")
    (db / "cs(card1)@skill_eff.json").write_text(json.dumps([{"id": "cs00_0004_01", "eff": "SKILL_EFF_DMG", "eff_attr": "DMG_ATTR_FIX", "eff_value": "50"}]), encoding="utf-8")
    (db / "constant_metagame@constant_meta.json").write_text(json.dumps([{"id": "lead_pct", "value": "50"}]), encoding="utf-8")
    text = tmp_path / "text" / "en"
    text.mkdir(parents=True)
    (text / "text.json").write_text(json.dumps([{"id": key, "text": value} for key, value in TEXT.items()]), encoding="utf-8")
    return Context(tmp_path)


def _source(ctx: Context, fields: dict) -> tuple:
    """
    `source_text` with the fixture's constants.

    Args:
        ctx: The fixture context.
        fields: The term's override fields.

    Returns:
        (term, definition, unresolved placeholders).
    """
    return glossary.source_text(ctx, fields, {"lead_pct": "50"})


def _overrides(entries: dict) -> Overrides:
    """
    Glossary overrides holding `entries`, each given a `_why`.

    Args:
        entries: Override key -> fields.

    Returns:
        The overrides.
    """
    return Overrides("glossary", {key: {**fields, "_why": "test"} for key, fields in entries.items()})


def _term(**fields) -> dict:
    """
    Override fields for one term, with a valid category and no links unless given.

    Args:
        **fields: Fields to add or replace.

    Returns:
        The fields.
    """
    return {"category": "mechanic", "aliases": [], "seeAlso": [], **fields}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Reading client text


def test_tooltip_resolves_values_from_its_linked_status(tmp_path):
    term, definition, unresolved = _source(_context(tmp_path), {"tooltip": "T_CS00_0004"})
    assert term == "Agony"
    assert definition == "At the end of the turn, 50 Fixed DoT. Max 20 stacks."
    assert unresolved == []


def test_tooltip_falls_back_to_later_description_columns_and_fills_constants(tmp_path):
    term, definition, _ = _source(_context(tmp_path), {"tooltip": "TALENT_LEAD"})
    assert term == "Lead"
    assert definition == "50% chance to decrease Cost by 1."


def test_tooltip_without_a_row_reads_its_text_keys_and_drops_the_trigger_colon(tmp_path):
    term, definition, _ = _source(_context(tmp_path), {"tooltip": "CARD_WHEN_BREAK"})
    assert term == "Attunement"
    assert definition == "When this card is Drawn, activate effect."


def test_stack_cap_comes_from_the_linked_status(tmp_path):
    _, definition, unresolved = _source(_context(tmp_path), {"tooltip": "T_CS00_0369"})
    assert definition == "Halve Fracture stacks (max 30 stacks)."
    assert unresolved == []


def test_explicit_text_keys(tmp_path):
    ctx = _context(tmp_path)
    assert _source(ctx, {"term_key": "attribute_electric"}) == ("Instinct", None, [])
    assert _source(ctx, {"term_key": "help_menu@name@help_025", "definition_key": "tt_pg@desc@024"}) == ("Ravage", "Enemies become Ravaged.", [])


def test_unknown_tooltip_gives_nothing(tmp_path):
    assert _source(_context(tmp_path), {"tooltip": "NO_SUCH_TOOLTIP"}) == (None, None, [])


def test_fill_constants_only_touches_known_names():
    assert glossary.fill_constants("#lead_pct# and #ev_0# and #count#", {"lead_pct": "50", "count": "3"}) == "50% and #ev_0# and 3"


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Building entries


def test_entries_keep_file_order_and_written_text_wins():
    overrides = _overrides({
        "b": _term(tooltip="B", seeAlso=["a"]),
        "a": _term(tooltip="A", definition={"en": "Written."}, aliases=["A"]),
        "engraving:pe_0001": {"text": {"en": "Clarified."}},
    })
    found = {"A": ("Term A", "From client.", []), "B": ("Term B", "Client B.", [])}
    issues = []
    terms, clarifications = glossary.build_content(lambda fields: found[fields["tooltip"]], overrides, issues)
    assert issues == []
    assert [entry["id"] for entry in terms] == ["b", "a"]
    assert terms[1] == {"id": "a", "term": {"en": "Term A"}, "aliases": ["A"], "category": "mechanic", "definition": {"en": "Written."}, "seeAlso": []}
    assert clarifications == [{"kind": "engraving", "refId": "pe_0001", "text": {"en": "Clarified."}}]


def test_problems_are_reported():
    overrides = _overrides({
        "gone": _term(tooltip="GONE"),
        "partial": _term(tooltip="PARTIAL"),
        "same": _term(tooltip="SAME", term={"en": "Same"}),
        "odd": _term(term={"en": "Odd"}, definition={"en": "Odd."}, category="weird", seeAlso=["missing"]),
        "bogus:x": {"text": {"en": "Text."}},
    })
    found = {"GONE": (None, None, []), "PARTIAL": ("Partial", "Has #tv# left.", ["tv"]), "SAME": ("Same", "Same.", [])}
    issues = []
    terms, clarifications = glossary.build_content(lambda fields: found.get(fields.get("tooltip"), (None, None, [])), overrides, issues)
    messages = [(issue.level, issue.message) for issue in issues]
    assert ("error", "glossary: 'gone' names client text that does not exist") in messages
    assert ("error", "glossary: 'partial' has unresolved placeholders ['tv']") in messages
    assert ("warning", "glossary: 'same' term override equals the client text and can be removed") in messages
    assert any(level == "error" and "'odd' has category 'weird'" in message for level, message in messages)
    assert ("error", "glossary: 'odd' has a seeAlso link to unknown term 'missing'") in messages
    assert any(level == "error" and "clarification 'bogus:x'" in message for level, message in messages)
    assert len(terms) == 4 and clarifications == []
