"""
Read access to the extracted game client for the generators.

Wraps the raw shard files and the English text catalogue, and cleans up the client's text quirks once so no generator
has to. Every table is cached for the life of the object, since several generators read the same shards.
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path

# The client's text export mangles curly apostrophes into the replacement character, and some names carry zero-width
# spaces. Both are fixed on the way out of `text()`.
_TEXT_FIXES = {"�": "'", "‘": "'", "’": "'", "“": '"', "”": '"', "​": "", "﻿": ""}

_LIST_ITEM = re.compile(r"[^\[\],\s]+")

# The game constants table, read for placeholders such as `#lead_pct#` and for ids such as the fallback epiphany.
CONSTANTS_TABLE = "constant_metagame@constant_meta.json"

# An epiphany variant row id, such as `rsp3_c_1008_srt4`, whose digits are the variant's level.
_VARIANT_ROW = re.compile(r"^rsp(\d+)(?:_|$)")


def parse_list(raw: str | None) -> list[str]:
    """
    Split a client list cell such as `[c_1008_srt4_01,c_1008_srt4_02]` into its items.

    Args:
        raw: The cell as stored, which may also be "none", "[]" or empty.

    Returns:
        The items in order, with "none" placeholders dropped.
    """
    if not raw:
        return []
    return [item for item in _LIST_ITEM.findall(raw) if item != "none"]


def clean_text(text: str) -> str:
    """
    Fix the character-level quirks in a client string.

    Args:
        text: A raw string from the text catalogue.

    Returns:
        The string with apostrophes, quotes and invisible characters repaired.
    """
    for bad, good in _TEXT_FIXES.items():
        text = text.replace(bad, good)
    return text


class Client:
    """One extracted game client, read lazily."""

    def __init__(self, root: Path):
        """
        Args:
            root: The extraction folder, holding `db/` and `text/en/text.json`.
        """
        self.root = Path(root)
        self.db = self.root / "db"
        self._by_id: dict[str, dict[str, dict]] = {}

    def rows(self, name: str) -> list[dict]:
        """
        One shard file.

        Args:
            name: The file name inside `db/`, such as "r_spark@r_spark.json".

        Returns:
            Its rows in file order, or an empty list when the file is missing.
        """
        return self._load(name)

    def by_id(self, name: str) -> dict[str, dict]:
        """
        One shard file keyed by its `id` column.

        Args:
            name: The file name inside `db/`.

        Returns:
            id -> row, built once per file. Callers must not mutate it.
        """
        if name not in self._by_id:
            self._by_id[name] = {row["id"]: row for row in self._load(name) if "id" in row}
        return self._by_id[name]

    def union(self, suffix: str, prefix: str = "") -> dict[str, dict]:
        """
        Every shard whose name ends with `suffix`, merged and keyed by id.

        The client splits one logical table across many files, one per author or content drop, such as
        `card(ikarus)@card.json` and `card(domi)@card.json`.

        Args:
            suffix: The table part of the file name, such as "@card.json".
            prefix: Optionally, a required start of the file name, such as "card(".

        Returns:
            id -> row across all matching shards. Later files win on a duplicate id.
        """
        merged: dict[str, dict] = {}
        for path in sorted(self.db.glob(f"{prefix}*{suffix}")):
            if "@" not in path.name:
                continue
            for row in self._load(path.name):
                if "id" in row:
                    merged[row["id"]] = row
        return merged

    @cached_property
    def cards(self) -> dict[str, dict]:
        """Every card row, across all `card(*)@card.json` shards."""
        return self.union("@card.json", "card(")

    @cached_property
    def effects(self) -> dict[str, dict]:
        """Every skill effect row, across all `*@skill_eff.json` shards."""
        return self.union("@skill_eff.json")

    @cached_property
    def statuses(self) -> dict[str, dict]:
        """Every status (cs) row, across all `*@cs.json` shards."""
        return self.union("@cs.json")

    @cached_property
    def tooltips(self) -> dict[str, dict]:
        """Every tooltip row, across all `*@tooltip.json` shards."""
        return self.union("@tooltip.json")

    @cached_property
    def synergies(self) -> dict[str, dict]:
        """Every synergy tier row, such as Season 4's "3+ Inquiry", across all `*@synergy_define.json` shards."""
        return self.union("@synergy_define.json")

    @cached_property
    def card_r_spark(self) -> dict[str, dict]:
        """Every epiphany variant row, across all `*@card_r_spark.json` shards."""
        return self.union("@card_r_spark.json")

    @cached_property
    def variants_by_base(self) -> dict[str, list[tuple[int, str]]]:
        """Base card id -> its (level, variant card id) pairs in level order, for variants whose card exists in the client."""
        grouped: dict[str, list[tuple[int, str]]] = {}
        for row_id, row in self.card_r_spark.items():
            match = _VARIANT_ROW.match(row_id)
            target = row.get("change_link_card_id")
            if match and target in self.cards:
                grouped.setdefault(row.get("link_card_id"), []).append((int(match.group(1)), target))
        return {base: sorted(levels) for base, levels in grouped.items()}

    @cached_property
    def constants(self) -> dict[str, str]:
        """Constant id -> value, from the game constants table."""
        return {row["id"]: row.get("value", "") for row in self.rows(CONSTANTS_TABLE) if "id" in row}

    def illustration(self, card: dict, columns: tuple[str, ...] = ("sct_name", "spine_model")) -> Path | None:
        """
        A card's full-size illustration.

        Args:
            card: The card row.
            columns: The columns that may name the illustration, tried in order.

        Returns:
            The first `card_illustration/<name>.png` that exists, or None when none does.
        """
        for column in columns:
            name = card.get(column)
            if name and name != "none":
                path = self.root / "card_illustration" / f"{name}.png"
                if path.is_file():
                    return path
        return None

    @cached_property
    def _text(self) -> dict[str, str]:
        path = self.root / "text" / "en" / "text.json"
        rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        # Rows reference text keys in upper case while the catalogue stores them in lower case, so index by lower case.
        return {str(row["id"]).lower(): row.get("text") or "" for row in rows if row.get("id")}

    def text(self, key: str | None) -> str | None:
        """
        One English string from the text catalogue.

        Args:
            key: A text key such as "card@desc@c_1055_srt1", in any case.

        Returns:
            The cleaned string, or None when the key is empty, "none" or not in the catalogue.
        """
        if not key or key == "none":
            return None
        raw = self._text.get(key.lower())
        return clean_text(raw) if raw else None

    def has_text(self) -> bool:
        """
        Whether the text catalogue is present.

        Returns:
            True if `text/en/text.json` exists.
        """
        return (self.root / "text" / "en" / "text.json").is_file()

    def _load(self, name: str) -> list[dict]:
        cache = self.__dict__.setdefault("_file_cache", {})
        if name not in cache:
            path = self.db / name
            cache[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        return cache[name]
