"""
The deck builder's common and divine epiphany lists.

Both come from the client's `r_spark` table. Rows with no god are common epiphanies, offered in cost buckets per effect.
Rows tied to a god are divine epiphanies. Descriptions are the client's own templates, resolved and tidied.

Saved decks and exported deck files store the chosen epiphany by its `id`, so an id must never change under a user. Each
entry records its client row in `source_key`, and a re-run reuses whatever id that row already has. The hand-made files
this replaced used numbered ids with a scraped hash as `source_key`. Those entries are matched to client rows once, by
level, card type and wording, so their ids carry over. A row with no earlier id gets one derived from its client row id.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from scripts.datagen.client import parse_list
from scripts.datagen.naming import CARD_TYPES
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes

NAME = "epiphanies"
OFFLINE = True

COMMON_PATH = Path("src/pages/deck-builder/data/deck-builder-common-epiphanies.json")
DIVINE_PATH = Path("src/pages/deck-builder/data/deck-builder-divine-epiphanies.json")

SPARK_TABLE = "r_spark@r_spark.json"
GOD_TABLE = "r_spark_god_type_define@r_spark_god_type_define.json"
CLASS_TABLE = "base_class_define@base_class_define.json"

# The constant naming the epiphany the game hands out when no other one fits a card. Its roll weight is 0, but it is still
# a real outcome, so it is kept.
PICK_FAIL_CONSTANT = "r_spark_pick_fail_id"

COMMON_PREFIX = "com_"
DIVINE_PREFIX = "div_"

# The deck builder's cost labels, from `getCardLevel()` in VariantSettingsModal.tsx. It files X-cost cards (cost -1)
# under "0", so there is no separate X label. An entry valid at every cost gets no labels at all.
ALL_LEVELS = ["0", "1", "2", "3", "4+"]

# Minimum wording similarity, 0 to 1, for a hand-made entry to hand its id to a client row.
MATCH_THRESHOLD = 0.5

# Row columns, beyond the generated fields, that decide which cards an epiphany can land on. Two rows equal in all of
# them and in their generated entry are the same epiphany to the deck builder.
_FILTER_COLUMNS = ("god_type", "target_card_include_talent", "target_card_exclude_talent", "r_spark_tag", "r_spark_exclude_tag", "link_extra_tag_id")

# Generic common rows. Rows such as `c_30047_05013` copy a generic row for one card only (Nine's Hew, through the
# `nine_exhaust` tag), which the deck builder cannot express, so they are left out.
_COMMON_ROW = re.compile(r"^c\d{5}$")

# The hand-made files stored a 12-character scraped hash as `source_key`. Only those entries go through wording matching.
_LEGACY_KEY = re.compile(r"^[0-9a-f]{12}$")

# The hand-made common file labelled the cost 0 bucket "1, 2, 3, 4+" and the fallback epiphany "X, 1". These are the
# labels those entries really meant, used only when matching them to client rows.
_LEGACY_COMMON_LEVELS = {("1", "2", "3", "4+"): ["0"], ("X", "1"): ["0", "1"]}

_WORD = re.compile(r"[a-z0-9%+]+")
_GOD_NAME = re.compile(r"^(.+?)'s? Epiphany$")


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Build


def build(ctx: Context) -> TargetResult:
    """
    Generate both epiphany files.

    Args:
        ctx: The run context.

    Returns:
        The two files, a summary, and any unresolved placeholders, dropped ids or invalid overrides as issues.
    """
    overrides = ctx.overrides(NAME)
    issues: list[Issue] = []
    unresolved: dict[str, list[str]] = {}
    rows = [row for row in ctx.client.rows(SPARK_TABLE) if overrides.keeps(row["id"])]
    pick_fail = ctx.client.constants.get(PICK_FAIL_CONSTANT)
    classes = {row["id"]: ctx.client.text(row.get("class_name")) or row["id"].title() for row in ctx.client.rows(CLASS_TABLE)}
    gods = {row["id"]: god_name(ctx.client.text(row.get("name")), row["id"]) for row in ctx.client.rows(GOD_TABLE)}

    common_rows = [row for row in rows if row.get("god_type") == "none" and (row["id"] == pick_fail or (_COMMON_ROW.match(row["id"]) and _rollable(row)))]
    divine_rows = [row for row in rows if row.get("god_type") not in (None, "", "none") and _rollable(row)]
    # Group divine epiphanies by god, keeping the client's order inside each god.
    divine_rows.sort(key=lambda row: row["god_type"].title())

    common = drop_duplicates([(row, _entry(ctx, row, classes, None, unresolved)) for row in common_rows])
    divine = drop_duplicates([(row, _entry(ctx, row, classes, gods, unresolved)) for row in divine_rows])

    outputs: dict[Path, list[dict]] = {}
    for path, prefix, entries, legacy_levels in ((COMMON_PATH, COMMON_PREFIX, common, _LEGACY_COMMON_LEVELS), (DIVINE_PATH, DIVINE_PREFIX, divine, None)):
        ids, dropped = assign_ids(entries, _existing(path), prefix, legacy_levels)
        outputs[path] = [{"id": ids[entry["source_key"]], **entry} for entry in entries]
        if dropped:
            issues.append(Issue("warning", f"{NAME}: hand-made ids with no client row any more: {', '.join(dropped)}"))

    # One overrides file covers both outputs, so it is validated against both at once.
    generated = {entry["id"]: entry for entries in outputs.values() for entry in entries}
    issues.extend(overrides.validate(generated))
    for entry in generated.values():
        issues.extend(overrides.unresolved(entry["id"], entry["source_key"], unresolved.get(entry["source_key"], [])))
    applied = overrides.apply(generated)
    files = {path: json_bytes([applied[entry["id"]] for entry in entries]) for path, entries in outputs.items()}
    return TargetResult(files, f"{len(outputs[COMMON_PATH])} common, {len(outputs[DIVINE_PATH])} divine epiphanies", issues)


def _entry(ctx: Context, row: dict, classes: dict[str, str], gods: dict[str, str] | None, unresolved: dict[str, list[str]]) -> dict:
    """
    One epiphany in the output format, without its id.

    Args:
        ctx: The run context.
        row: The `r_spark` row.
        classes: Class id -> display name.
        gods: God id -> display name, for a divine epiphany. None for a common one.
        unresolved: Collects the placeholders each row could not fill, keyed by row id.

    Returns:
        The entry. Common entries carry `section` fields, divine ones `god` fields.
    """
    template = ctx.client.text(row.get("description")) or ""
    resolution = ctx.resolver.resolve(template, parse_list(row.get("add_link_skill_eff_id")))
    if resolution.unresolved:
        unresolved[row["id"]] = resolution.unresolved
    description = ctx.text(resolution.text)
    rarity = row.get("rarity", "").removeprefix("R_SPARK_RARITY_").title()
    card_types = [CARD_TYPES[category] for category in parse_list(row.get("target_card_category")) if category in CARD_TYPES]
    allowed_classes = [classes.get(class_id, class_id.title()) for class_id in parse_list(row.get("target_link_base_class_define_id"))]
    levels = level_labels(int(row.get("target_card_cost_min", -1)), int(row.get("target_card_cost_max", 99)))
    tags = [title for talent in parse_list(row.get("add_talent")) if talent != "TALENT_NONE" and (title := ctx.resolver.talent_title(talent))]

    if gods is None:
        heading = {"section": "Other", "display_section": "Other"}
        label = []
    else:
        god = row["god_type"]
        heading = {"god": god.title(), "display_god": gods.get(god, god.title())}
        label = [heading["display_god"]]
    raw_text = "\n".join([description, *label, rarity.upper(), *card_types, *allowed_classes, *levels])
    return {
        **heading,
        "description": description,
        "rarity": rarity,
        "card_types": card_types,
        "allowed_classes": allowed_classes,
        "levels": levels,
        "tags": tags,
        "source_key": row["id"],
        "raw_text": raw_text,
    }


def _rollable(row: dict) -> bool:
    """Whether the game can roll this row. A roll weight of 0 means it is never offered."""
    return row.get("r_spark_ratio", "0") not in ("0", "", "none")


def _existing(path: Path) -> list[dict]:
    """The entries currently on disk for an output file, or an empty list when it does not exist yet."""
    full = REPO_ROOT / path
    return json.loads(full.read_text(encoding="utf-8")) if full.is_file() else []


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Pure helpers


def level_labels(cost_min: int, cost_max: int) -> list[str]:
    """
    The deck builder's cost labels covered by a row's cost range.

    Args:
        cost_min: `target_card_cost_min`, where -1 is an X-cost card.
        cost_max: `target_card_cost_max`, where 99 means no upper limit.

    Returns:
        The labels in `ALL_LEVELS` order. X-cost cards count as "0", as they do in the deck builder. A range covering
        every label gives an empty list, which the deck builder reads as "any cost".
    """
    labels = []
    for cost, label in ((-1, "0"), (0, "0"), (1, "1"), (2, "2"), (3, "3")):
        if cost_min <= cost <= cost_max and label not in labels:
            labels.append(label)
    if cost_max >= 4:
        labels.append("4+")
    return [] if labels == ALL_LEVELS else labels


def god_name(text: str | None, god_id: str) -> str:
    """
    A god's display name from its epiphany title, such as "Vytor" from "Vytor's Epiphany".

    Args:
        text: The `fate_god_type_define@name@<god>` text, or None when the client has none.
        god_id: The god id, used as a fallback.

    Returns:
        The name.
    """
    match = _GOD_NAME.match(text or "")
    return match.group(1) if match else (text or god_id.title())


def drop_duplicates(pairs: list[tuple[dict, dict]]) -> list[dict]:
    """
    Keep one entry per distinct epiphany.

    The X-cost bucket of each common effect repeats its cost 0 bucket exactly, and the deck builder files X-cost cards
    under "0" anyway, so the two collapse into one entry here.

    Args:
        pairs: (row, entry) in output order.

    Returns:
        The entries, without any whose generated fields and card filters repeat an earlier one.
    """
    seen = set()
    kept = []
    for row, entry in pairs:
        key = json.dumps([{k: v for k, v in entry.items() if k != "source_key"}, [row.get(column) for column in _FILTER_COLUMNS]], sort_keys=True)
        if key not in seen:
            seen.add(key)
            kept.append(entry)
    return kept


def description_similarity(left: str, right: str) -> float:
    """
    How alike two descriptions read, ignoring case and punctuation.

    Args:
        left: One description.
        right: The other.

    Returns:
        0 for nothing in common up to 1 for the same words in the same order.
    """
    return difflib.SequenceMatcher(None, _WORD.findall(left.lower()), _WORD.findall(right.lower())).ratio()


def assign_ids(entries: list[dict], existing: list[dict], prefix: str, legacy_levels: dict[tuple, list[str]] | None = None) -> tuple[dict[str, str], list[str]]:
    """
    Pick each entry's id so ids already saved in users' decks keep pointing at the same epiphany.

    Args:
        entries: The generated entries, each with its client row id in `source_key`.
        existing: The entries currently in the output file.
        prefix: The id prefix for rows with no earlier id, such as "com_".
        legacy_levels: For common epiphanies, the corrected levels of hand-made entries whose labels were wrong. When given,
            a hand-made entry only matches a row with the same levels.

    Returns:
        source_key -> id for every entry, and the ids of hand-made entries that matched no row.
    """
    keys = {entry["source_key"] for entry in entries}
    ids: dict[str, str] = {}
    taken: set[str] = set()
    for old in existing:
        key = old.get("source_key")
        if key in keys and key not in ids and old["id"] not in taken:
            ids[key] = old["id"]
            taken.add(old["id"])

    legacy = [old for old in existing if _LEGACY_KEY.match(str(old.get("source_key", ""))) and old["id"] not in taken]
    candidates = []
    for index, entry in enumerate(entries):
        if entry["source_key"] in ids:
            continue
        for old in legacy:
            old_levels = (legacy_levels or {}).get(tuple(old.get("levels", [])), old.get("levels", []))
            if old.get("god") != entry.get("god") or (legacy_levels is not None and old_levels != entry["levels"]):
                continue
            similarity = description_similarity(entry["description"], old.get("description", ""))
            if similarity < MATCH_THRESHOLD:
                continue
            same = [sorted(old.get(name, [])) == sorted(entry[name]) for name in ("card_types", "allowed_classes")]
            score = similarity + 0.25 * sum(same) + 0.25 * (old_levels == entry["levels"])
            candidates.append((-score, old["id"], index))
    # Best matches first. Ties go to the lower id, then to the earlier row, so the result never depends on dict order.
    for _, old_id, index in sorted(candidates):
        key = entries[index]["source_key"]
        if key not in ids and old_id not in taken:
            ids[key] = old_id
            taken.add(old_id)

    for entry in entries:
        ids.setdefault(entry["source_key"], prefix + entry["source_key"])
    return ids, [old["id"] for old in legacy if old["id"] not in taken]
