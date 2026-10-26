"""
The Simulator's enemy presets: DEF and damage decrease for each level of the farming, boss and disaster stages.

Both values come straight from the client's `mon_stat` table. The damage decrease is stored per row and does not follow
DEF across content types, so the Simulator uses it as-is instead of estimating it from DEF.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult, json_bytes

NAME = "enemy_presets"
OFFLINE = True

OUTPUT_PATH = Path("src/pages/simulator/data/simulator-enemy-presets.json")
MON_STAT = "mon_stat@mon_stat.json"

# Preset groups in display order: group name, the `mon_stat` id pattern, and the button label prefix. A `season` group
# keeps only the latest season's rows.
GROUPS = (
    ("combat", re.compile(r"combat_exp_(?P<level>\d+)"), "Lv"),
    ("gold", re.compile(r"gold_(?P<level>\d+)"), "Lv"),
    ("piece", re.compile(r"piece_\d+_(?P<level>\d+)"), "Lv"),
    ("hyperspace", re.compile(r"hyperspace_\d+_(?P<level>\d+)"), "Lv"),
    ("boss", re.compile(r"boss_\d+_(?P<level>\d+)"), "Lv"),
    ("disaster", re.compile(r"disaster_rank_s(?P<season>\d+)_(?P<level>\d+)"), "R"),
)


def build(ctx: Context) -> TargetResult:
    """
    Generate the enemy presets file.

    Args:
        ctx: The run context.

    Returns:
        The file, a summary, and an issue for each group with no rows or with variants that disagree on a level.
    """
    rows = ctx.client.rows(MON_STAT)
    issues: list[Issue] = []
    groups = []
    for name, pattern, prefix in GROUPS:
        presets = _presets(name, pattern, prefix, rows, issues)
        if presets:
            groups.append({"group": name, "presets": presets})
        else:
            issues.append(Issue("error", f"{NAME}: no {MON_STAT} rows for the {name} group"))
    return TargetResult({OUTPUT_PATH: json_bytes(groups)}, _summary(groups), issues)


def _presets(name: str, pattern: re.Pattern, prefix: str, rows: list[dict], issues: list[Issue]) -> list[dict]:
    """
    The presets of one group, one per level.

    Args:
        name: The group name, used in issue messages.
        pattern: The `mon_stat` id pattern, with a `level` group and an optional `season` group.
        prefix: The label prefix, such as "Lv".
        rows: Every `mon_stat` row.
        issues: Variants that disagree on a level are reported here.

    Returns:
        The presets sorted by level, or a single "All" preset when every level has the same stats.
    """
    matches = [(match, row) for row in rows if (match := pattern.fullmatch(row.get("id", "")))]
    if "season" in pattern.groupindex and matches:
        latest = max(int(match["season"]) for match, _ in matches)
        matches = [(match, row) for match, row in matches if int(match["season"]) == latest]

    by_level: dict[int, dict] = {}
    for match, row in sorted(matches, key=lambda pair: pair[1]["id"]):
        level = int(match["level"])
        stats = {"def": round(float(row["stat_def"])), "dmg_decrease": float(row["dmg_decrease_rate"])}
        if level not in by_level:
            by_level[level] = stats
        elif by_level[level] != stats:
            issues.append(Issue("warning", f"{NAME}: {name} {prefix}{level} variants disagree, keeping {by_level[level]} over {row['id']}"))

    distinct = {tuple(stats.values()) for stats in by_level.values()}
    if len(by_level) > 1 and len(distinct) == 1:
        return [{"label": "All", **next(iter(by_level.values()))}]
    return [{"label": f"{prefix}{level}", **by_level[level]} for level in sorted(by_level)]


def _summary(groups: list[dict]) -> str:
    """
    One line describing the generated presets against the file on disk.

    Args:
        groups: The generated groups.

    Returns:
        Such as "6 groups, 45 presets (was 44)".
    """
    path = REPO_ROOT / OUTPUT_PATH
    current = sum(len(group["presets"]) for group in json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else 0
    total = sum(len(group["presets"]) for group in groups)
    return f"{len(groups)} groups, {total} presets (was {current})"
