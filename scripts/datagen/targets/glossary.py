"""
The Encyclopedia's glossary and its hand-written clarifications.

The client has no glossary, so the term list itself lives in `api/data/overrides/glossary.json`. Each term there names
the tooltip (or text keys) it comes from, and this target fills in the English name and definition from the client,
resolved and tidied. Category, aliases and see-also links are editorial and copied as they are. Terms the client has no
text for carry their own `term` and `definition`, and those win over anything generated.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.datagen.client import parse_list
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.runner import Context, TargetResult, json_bytes

NAME = "glossary"
OFFLINE = True

CONTENT_PATH = Path("src/pages/encyclopedia/data/encyclopedia-content.json")

# The values the frontend's `GlossaryCategory` and `ClarificationKind` types allow.
CATEGORIES = ("status", "card-type", "mechanic")
CLARIFICATION_KINDS = ("equipment", "engraving", "card")

# Tooltip description columns, most general first. The battle variants often read live values such as the stack count.
DESC_FIELDS = ("desc", "desc_outgame", "desc_battle", "desc_battle_monster")

_TOKEN = re.compile(r"#([A-Za-z0-9_]+)#")


def build(ctx: Context) -> TargetResult:
    """
    Generate the encyclopedia content file.

    Args:
        ctx: The run context.

    Returns:
        The file, a summary, and any missing client text, unresolved placeholders or invalid overrides as issues.
    """
    overrides = ctx.overrides(NAME)
    issues = overrides.validate({}, keyed_by_output=False)
    glossary, clarifications = build_content(lambda fields: source_text(ctx, fields, ctx.client.constants), overrides, issues)
    from_client = sum(1 for key, fields in overrides.entries.items() if ":" not in key and isinstance(fields, dict) and "definition" not in fields)
    summary = f"{len(glossary)} terms ({from_client} defined by the client), {len(clarifications)} clarifications"
    return TargetResult({CONTENT_PATH: json_bytes({"glossary": glossary, "clarifications": clarifications})}, summary, issues)


def build_content(lookup, overrides: Overrides, issues: list[Issue]) -> tuple[list[dict], list[dict]]:
    """
    Turn the overrides file into glossary and clarification entries, in file order.

    Args:
        lookup: Called with a term's override fields. Returns (term, definition, unresolved placeholders) from the client,
            with None for whatever the client has no text for.
        overrides: The glossary overrides.
        issues: Problems are appended here.

    Returns:
        The glossary entries and the clarification entries.
    """
    glossary: list[dict] = []
    clarifications: list[dict] = []
    for key, fields in overrides.entries.items():
        if not isinstance(fields, dict):
            continue
        if ":" in key:
            clarification = _clarification(key, fields, issues)
            if clarification:
                clarifications.append(clarification)
        else:
            glossary.append(_term(key, fields, lookup(fields), issues))

    known = {entry["id"] for entry in glossary}
    for entry in glossary:
        for ref in entry["seeAlso"]:
            if ref not in known:
                issues.append(Issue("error", f"{NAME}: '{entry['id']}' has a seeAlso link to unknown term '{ref}'"))
    return glossary, clarifications


def source_text(ctx: Context, fields: dict, constants: dict[str, str]) -> tuple[str | None, str | None, list[str]]:
    """
    A term's name and definition as the client writes them.

    Args:
        ctx: The run context.
        fields: The term's override fields. `tooltip` names a tooltip id, and `term_key` / `definition_key` name text keys
            directly, taking precedence over the tooltip.
        constants: The client's game constants, for placeholders such as `#lead_pct#`.

    Returns:
        The tidied term, the tidied definition, and the placeholders the definition still contains. Term or definition
        is None when the client has no text for it.
    """
    tooltip_id = fields.get("tooltip")
    row = ctx.client.tooltips.get(tooltip_id, {}) if tooltip_id else {}
    title_key = fields.get("term_key")
    if not title_key and tooltip_id:
        title_key = row.get("title") or f"tooltip@title@{tooltip_id}"
    desc_keys = [fields["definition_key"]] if fields.get("definition_key") else []
    if not desc_keys and tooltip_id:
        # Some tooltips (such as the engraving triggers) have text keys but no row.
        desc_keys = [row.get(column) for column in DESC_FIELDS] if row else [f"tooltip@{column}@{tooltip_id}" for column in DESC_FIELDS]

    term = None
    title = ctx.client.text(title_key)
    if title:
        term = ctx.text(ctx.resolver.resolve(fill_constants(title, constants), []).text, sentences=False).rstrip(":").strip() or None

    template = next((text for text in map(ctx.client.text, desc_keys) if text), None)
    if template is None:
        return term, None, []
    status = ctx.client.statuses.get(row.get("link_cs_id", "")) if row else None
    effects = parse_list(status.get("link_skill_eff_id")) if status else []
    resolution = ctx.resolver.resolve(fill_constants(template, constants), effects)
    return term, ctx.text(resolution.text) or None, resolution.unresolved


def fill_constants(template: str, constants: dict[str, str]) -> str:
    """
    Fill placeholders that name a game constant, such as `#lead_pct#`.

    Args:
        template: A client text template.
        constants: Constant id -> value, from the client's constants table.

    Returns:
        The template with those placeholders replaced. Constants ending in `_pct` gain a "%". Other placeholders are left.
    """

    def fill(match: re.Match) -> str:
        name = match.group(1)
        if name not in constants:
            return match.group(0)
        return f"{constants[name]}%" if name.endswith("_pct") else constants[name]

    return _TOKEN.sub(fill, template)


def _term(term_id: str, fields: dict, found: tuple[str | None, str | None, list[str]], issues: list[Issue]) -> dict:
    """
    One glossary entry.

    Args:
        term_id: The term's id.
        fields: Its override fields.
        found: The client's (term, definition, unresolved placeholders) for it.
        issues: Problems are appended here.

    Returns:
        The entry in the content file's format.
    """
    term, definition, unresolved = found
    has_source = any(key in fields for key in ("tooltip", "term_key", "definition_key"))
    written_term = fields.get("term", {}).get("en")
    written_definition = fields.get("definition", {}).get("en")

    if has_source and term is None and definition is None:
        issues.append(Issue("error", f"{NAME}: '{term_id}' names client text that does not exist"))
    if unresolved and written_definition is None:
        issues.append(Issue("error", f"{NAME}: '{term_id}' has unresolved placeholders {unresolved}"))
    if written_term is not None and written_term == term:
        issues.append(Issue("warning", f"{NAME}: '{term_id}' term override equals the client text and can be removed"))
    if written_definition is not None and written_definition == definition:
        issues.append(Issue("warning", f"{NAME}: '{term_id}' definition override equals the client text and can be removed"))
    if fields.get("category") not in CATEGORIES:
        issues.append(Issue("error", f"{NAME}: '{term_id}' has category {fields.get('category')!r}, expected one of {CATEGORIES}"))

    term = written_term or term
    definition = written_definition or definition
    if not term or not definition:
        issues.append(Issue("error", f"{NAME}: '{term_id}' has no {'term' if not term else 'definition'}"))
    return {
        "id": term_id,
        "term": {"en": term or ""},
        "aliases": list(fields.get("aliases", [])),
        "category": fields.get("category", ""),
        "definition": {"en": definition or ""},
        "seeAlso": list(fields.get("seeAlso", [])),
    }


def _clarification(key: str, fields: dict, issues: list[Issue]) -> dict | None:
    """
    One clarification entry.

    Args:
        key: The override key, `<kind>:<refId>`.
        fields: Its override fields, holding `text`.
        issues: Problems are appended here.

    Returns:
        The entry in the content file's format, or None when the key or text is invalid.
    """
    kind, ref_id = key.split(":", 1)
    text = fields.get("text", {}).get("en", "").strip()
    if kind not in CLARIFICATION_KINDS or not ref_id or not text:
        issues.append(Issue("error", f"{NAME}: clarification '{key}' needs a kind in {CLARIFICATION_KINDS}, a refId and text.en"))
        return None
    return {"kind": kind, "refId": ref_id, "text": {"en": text}}
