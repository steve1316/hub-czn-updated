"""
The fixed cleanup pass every generated description goes through after its template is filled in.

The rules are deterministic, so the same source text always tidies to the same result, and they live in
`data/tidy.json` so a new rule is a data change rather than a hand edit to some description.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

RULES_PATH = Path(__file__).parent / "data" / "tidy.json"

_SPACES = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?%])")
_SENTENCE_END = (".", "!", "?", ":")

# A count glued to the next word, as in "3Vulnerable" or "1turn". Ordinals such as "2nd" are left alone.
_NUMBER_JOINED_TO_WORD = re.compile(r"(?<![\w.])(\d+)(?!st\b|nd\b|rd\b|th\b)([A-Za-z]{2,})")
# A hit-count sign left at the end of a line after its battle-only count was dropped.
_DANGLING_TIMES = re.compile(r"\s+[x×]\s*$", re.MULTILINE)


def _word_pattern(words: dict[str, str]) -> re.Pattern | None:
    """
    One case-insensitive pattern matching any of the words as a whole word.

    Args:
        words: Word -> replacement.

    Returns:
        The pattern, with one group per word named `w<index>` in `words` order, or None when there are no words. Longer
        words come first in the alternation, so "shitty" wins over "shit".
    """
    if not words:
        return None
    ordered = sorted(enumerate(words), key=lambda item: len(item[1]), reverse=True)
    alternation = "|".join(f"(?P<w{index}>{re.escape(word)})" for index, word in ordered)
    return re.compile(rf"(?<![\w-])(?:{alternation})(?![\w-])", re.IGNORECASE)


@dataclass(frozen=True)
class TidyRules:
    """Word lists for the cleanup pass, loaded from `data/tidy.json`."""

    # Misspelling -> correct spelling, applied everywhere.
    typos: dict[str, str] = field(default_factory=dict)
    # Inconsistently cased term -> the casing to use everywhere.
    casing: dict[str, str] = field(default_factory=dict)
    # Swear word -> milder word, applied to Guides only.
    soften: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = RULES_PATH) -> "TidyRules":
        """
        Read the rules file.

        Args:
            path: The JSON file, defaulting to the one shipped beside this module.

        Returns:
            The rules.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(typos=raw.get("typos", {}), casing=raw.get("casing", {}), soften=raw.get("soften", {}))

    @cached_property
    def patterns(self) -> dict[str, re.Pattern | None]:
        """Each word list compiled once into a single pattern, keyed by "typos", "casing" and "soften"."""
        return {name: _word_pattern(getattr(self, name)) for name in ("typos", "casing", "soften")}


def tidy(text: str, rules: TidyRules, *, soften: bool = False, sentences: bool = True) -> str:
    """
    Clean up one generated description.

    Args:
        text: The resolved text. Lines are separated by "\n".
        rules: The word lists to apply.
        soften: Also apply the swear-softening list. Only Guides set this.
        sentences: Join the lines into sentences that each end with a period. Off for short labels such as names.

    Returns:
        The cleaned text.
    """
    # A percent the template wrote after a value that already carries one.
    text = text.replace("%%", "%")
    text = _DANGLING_TIMES.sub("", text)
    text = _NUMBER_JOINED_TO_WORD.sub(r"\1 \2", text)
    lines = [_SPACE_BEFORE_PUNCTUATION.sub(r"\1", _SPACES.sub(" ", line)).strip() for line in text.split("\n")]
    lines = _join_wrapped([line for line in lines if line])
    if sentences:
        lines = [line if line.endswith(_SENTENCE_END) else f"{line}." for line in lines]
    result = " ".join(lines) if sentences else "\n".join(lines)
    result = _replace_words(result, rules.typos, rules.patterns["typos"])
    result = _replace_words(result, rules.casing, rules.patterns["casing"], keep_case=False)
    if soften:
        result = _replace_words(result, rules.soften, rules.patterns["soften"])
    return result


def _join_wrapped(lines: list[str]) -> list[str]:
    """
    Undo line breaks the client put in the middle of a sentence.

    Args:
        lines: Non-empty, stripped lines.

    Returns:
        The lines, with any line that follows one ending in a comma, or that starts in lower case, joined onto the line
        before it with a space.
    """
    joined: list[str] = []
    for line in lines:
        if joined and (joined[-1].endswith(",") or line[0].islower()):
            joined[-1] = f"{joined[-1]} {line}"
        else:
            joined.append(line)
    return joined


def _replace_words(text: str, words: dict[str, str], pattern: re.Pattern | None, *, keep_case: bool = True) -> str:
    """
    Swap whole words case-insensitively.

    Args:
        text: The text to edit.
        words: Word -> replacement.
        pattern: `words` compiled by `_word_pattern`.
        keep_case: Give the replacement the matched word's leading case. Off for casing rules, whose whole point is the
            replacement's exact case.

    Returns:
        The edited text. A replacement is not matched again.
    """
    if pattern is None:
        return text
    replacements = list(words.values())

    def swap(match: re.Match) -> str:
        replacement = replacements[int(match.lastgroup[1:])]
        if not keep_case or not replacement:
            return replacement
        first = replacement[0].upper() if match.group(0)[0].isupper() else replacement[0].lower()
        return first + replacement[1:]

    return pattern.sub(swap, text)
