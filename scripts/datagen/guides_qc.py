"""
The Guides import's quality report: counts of the problems the importer still leaves in the guides it writes.

The importer prints one summary line after every run and writes the details to `client_db/.cache/guides/qc.md`, so a change to it
can be measured against the run before.
"""

from __future__ import annotations

import re
from collections import Counter

# Problem class -> what it counts, in report order.
CLASSES = {
    "unfolded_duplicates": "Rated card lists that show one card more than once without folding it into a ladder",
    "empty_ladders": "Epiphany ladders where every level has an empty note",
    "loose_numbered_lines": 'Prose lines like "Flow 2: ..." left under a card list instead of on a card',
    "unidentified_rated": "Pictures in rated rows that nothing identified",
    "short_ladders": "Ladders with fewer levels than the card has epiphanies",
}

# A prose line that looks like a note for one level of a listed card, such as "Flow 2: x", 'Truth 3" x' or "OUAT 1, x".
_LOOSE_LINE = re.compile(r"^\s*[A-Za-z][\w' ]{0,30}?\s*[:,\"]?\s*\d\s*[:,\"]")


def collect(guides: list[tuple[str, str, dict]], variants_of, unidentified_rated: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    The problems in the guides the importer wrote.

    Args:
        guides: (slug, name, guide) for every guide.
        variants_of: Card id -> its `epiphany.variants`, whose length less the base card is the card's epiphany count.
        unidentified_rated: Guide name -> the cells of pictures in rated rows that nothing identified.

    Returns:
        Problem class -> one line per problem, such as "Adelheid: card-ratings Protect Us x2". Every class in `CLASSES` is present.
    """
    found: dict[str, list[str]] = {key: [] for key in CLASSES}
    for _, name, guide in guides:
        for page in guide["sections"]:
            blocks = page["blocks"]
            for index, block in enumerate(blocks):
                if block["type"] != "card-list":
                    continue
                where = f"{name}: {page['id']}"
                counts = Counter(item["cardId"] for item in block["items"])
                for item in block["items"]:
                    ladder = item.get("epiphanies")
                    if not ladder:
                        continue
                    if all(not level["note"]["en"].strip() for level in ladder):
                        found["empty_ladders"].append(f"{where} {item.get('name', item['cardId'])}")
                    if len(ladder) < len(variants_of(item["cardId"])) - 1:
                        found["short_ladders"].append(f"{where} {item.get('name', item['cardId'])} has {len(ladder)} of {len(variants_of(item['cardId'])) - 1}")
                for card_id, count in counts.items():
                    if count > 1 and not any(item.get("epiphanies") for item in block["items"] if item["cardId"] == card_id):
                        found["unfolded_duplicates"].append(f"{where} {card_id} x{count}")
                after = blocks[index + 1] if index + 1 < len(blocks) else None
                if after and after["type"] == "prose":
                    found["loose_numbered_lines"].extend(f"{where} {line.strip()[:50]}" for line in after["body"]["en"].split("\n") if _LOOSE_LINE.match(line))
        found["unidentified_rated"].extend(f"{name}: {ref}" for ref in unidentified_rated.get(name, []))
    return found


def summary(found: dict[str, list[str]]) -> str:
    """
    The counts as one line.

    Args:
        found: The result of `collect`.

    Returns:
        A line such as "guides QC: unfolded_duplicates=35 empty_ladders=29 ...".
    """
    return "guides QC: " + " ".join(f"{key}={len(lines)}" for key, lines in found.items())


def report(found: dict[str, list[str]]) -> bytes:
    """
    The details as a Markdown page.

    Args:
        found: The result of `collect`.

    Returns:
        The page, one section per problem class listing each problem.
    """
    parts = ["# Guides QC\n"]
    for key, what in CLASSES.items():
        lines = found[key]
        parts.append(f"\n## {key} ({len(lines)})\n\n{what}.\n\n" + "".join(f"- {line}\n" for line in lines))
    return "".join(parts).encode("utf-8")
