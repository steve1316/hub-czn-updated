"""
Memory fragment sets named in the sheet's shorthand, such as "BlackWing", "Executioners", "BattleField Evo" or "Scrab".

A shorthand is only taken when exactly one set fits it, so anything unclear stays as the sheet's own text.
"""

from __future__ import annotations

import re

from api.game_data.sets import SETS

# Words too common in set names to tell sets apart.
_STOP_WORDS = {"of", "the", "to", "a", "and", "our", "first", "meeting"}
# A token this long may be a prefix of a set's word ("Evo"), and one this long may have one typo ("Scrab").
_PREFIX_LENGTH = 3
_TYPO_LENGTH = 5
_SEPARATOR = " | "


def find_set(label: str) -> int | None:
    """
    The set a shorthand names, when every word of it fits one set: the same word, its plural, a prefix or a one-letter typo.

    Args:
        label: One part of a sheet line, such as "Executioners".

    Returns:
        The set id, or None when no set or more than one fits.
    """
    tokens = [token for token in map(_plain, label.split()) if token]
    if not tokens:
        return None
    joined = "".join(tokens)
    hits: set[int] = set()
    for set_id, entry in SETS.items():
        words = [word for word in map(_plain, entry["name"].split()) if word and word not in _STOP_WORDS]
        if joined == "".join(words):
            return set_id
        # Every word of the shorthand must fit the set, so "Blink Flow" is not taken for Black Wing.
        if all(any(_close(token, word) for word in words) for token in tokens):
            hits.add(set_id)
    return hits.pop() if len(hits) == 1 else None


def set_line(text: str) -> list[dict] | None:
    """
    A one-line list of sets, such as "BlackWing | Executioners | Flex".

    Args:
        text: A prose line or section title.

    Returns:
        One item per part: the set's id, name, pieces, bonus and icon (when it has one) with the sheet's label, or just the label
        for a part that is not a set. None when the text is not such a line or names no set.
    """
    if _SEPARATOR not in text or "\n" in text:
        return None
    items = []
    for part in text.split(_SEPARATOR):
        label = part.strip()
        set_id = find_set(label)
        if set_id is None:
            items.append({"label": label})
            continue
        items.append(set_item(label, set_id))
    return items if any("setId" in item for item in items) else None


def set_item(label: str, set_id: int) -> dict:
    """
    One set as a set-list item.

    Args:
        label: The sheet's label for it, such as "Flex".
        set_id: The set's id.

    Returns:
        The label with the set's id, name, pieces, bonus and icon (when it has one). `flex` is true when the label says "Flex", as the set is then
        only the sheet's example.
    """
    entry = SETS[set_id]
    item = {"label": label, "setId": set_id, "name": entry["name"], "pieces": entry["pieces"], "bonus": entry["bonus"]}
    if re.search("flex", label, re.IGNORECASE):
        item["flex"] = True
    if entry.get("icon_path"):
        item["icon"] = entry["icon_path"]
    return item


def _plain(word: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"'s\b", "", word.lower()))


def _close(token: str, word: str) -> bool:
    if token in (word, word + "s"):
        return True
    if len(token) >= _PREFIX_LENGTH and word.startswith(token):
        return True
    return len(token) >= _TYPO_LENGTH and _edit_distance(token, word) <= 1


def _edit_distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        previous, row[0] = row[0], i
        for j in range(1, len(b) + 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] != b[j - 1]))
    return row[len(b)]
