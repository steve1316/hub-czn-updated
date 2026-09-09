"""Render an extracted entry as the Python source that goes into `characters.py` or `partners.py`.

`repr()` is close but not right: it quotes strings with apostrophes and puts nested tables on one
line, so the result never matches the file it is pasted into. These tables are read by hand far more
often than they are written, so the formatting is worth getting right at the source.
"""
from __future__ import annotations

import json

INDENT = "    "


def format_value(value, depth: int) -> str:
    """
    One value as repo-style Python source.

    Args:
        value: A string, number, `None`, tuple, or dict of those.
        depth: Indent level the value starts at, used to lay nested tables out.

    Returns:
        The source text, spread over several lines only for a non-empty dict.
    """
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None or isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, tuple):
        return "(" + ", ".join(format_value(item, depth) for item in value) + ")"
    if isinstance(value, dict):
        if not value:
            return "{}"
        pad = INDENT * (depth + 1)
        rows = "".join(f"{pad}{json.dumps(k, ensure_ascii=False)}: {format_value(v, depth + 1)},\n" for k, v in value.items())
        return "{\n" + rows + INDENT * depth + "}"
    raise TypeError(f"cannot format {type(value).__name__}")


def format_entry(res_id: int, entry: dict, keys: tuple[str, ...], comment: str = "") -> str:
    """
    A whole `res_id: {...},` block, ready to sit inside one of the game data tables.

    Args:
        res_id: The key the entry is stored under.
        entry: The extracted fields.
        keys: Which fields to emit, in the order the tables use.
        comment: Optional trailing comment on the opening line, for anything needing review.

    Returns:
        The block, indented one level, with no trailing newline.
    """
    head = f"{INDENT}{res_id}: {{" + (f"  # {comment}" if comment else "")
    lines = [head]
    for key in keys:
        lines.append(f"{INDENT * 2}{json.dumps(key, ensure_ascii=False)}: {format_value(entry[key], 2)},")
    lines.append(f"{INDENT}}},")
    return "\n".join(lines)
