"""
The simulator's eff type catalog: one entry per skill effect type the simulator models.

`scripts/build_eff_catalog_scaffold.py` owns the derivation. This target reruns its refresh of the automatic fields
(`client_instances`, `params_used`, `linked_conditions`, `linked_cs_ids`) against the configured client, and keeps the
hand-annotated fields (`trigger`, `effect`, `stack_rule`, `confidence`, `notes` and the rest), as the scaffold does on a
re-run.

Two inputs of the scaffold are machine-dependent, so they are pinned to the committed file instead:

- The scope. The scaffold picks eff types seen in local capture logs, which differ per machine. Here the scope is the set
  of eff types already in the catalog, so a new type is added by running the scaffold itself and annotating it.
- `observed_count`, which also comes from those capture logs. It is kept as committed.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import build_eff_catalog_scaffold as scaffold
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult

NAME = "eff_type_catalog"
OFFLINE = True

CATALOG_PATH = Path("api/data/eff_type_catalog.json")

# The fields this target recomputes from the client. Every other field is carried over from the committed file.
AUTO_FIELDS = ("client_instances", "params_used", "linked_conditions", "linked_cs_ids")


def build(ctx: Context) -> TargetResult:
    """
    Refresh the catalog's automatic fields from the client.

    Args:
        ctx: The run context.

    Returns:
        The catalog file, a summary of how many entries changed, and a warning for eff types the client no longer has.

    Raises:
        FileNotFoundError: If the catalog file does not exist, since it defines the scope.
    """
    path = REPO_ROOT / CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"{CATALOG_PATH} is missing. Create it with scripts/build_eff_catalog_scaffold.py first")
    existing = json.loads(path.read_text(encoding="utf-8"))
    by_type = scaffold.group_by_type(scaffold.load_skill_eff_instances(ctx.client.db))
    catalog, gone = refresh(existing, by_type)

    issues = []
    if gone:
        issues.append(Issue("warning", f"{NAME}: the client no longer has {', '.join(gone)}, so they were dropped"))
    changed = sum(1 for eff_type, entry in catalog.items() if any(entry[key] != existing[eff_type].get(key) for key in AUTO_FIELDS))
    summary = f"{len(catalog)} eff types, {changed} with refreshed client fields"
    return TargetResult({CATALOG_PATH: scaffold.render(catalog).encode("utf-8")}, summary, issues)


def refresh(existing: dict, by_type: dict[str, list[dict]]) -> tuple[dict, list[str]]:
    """
    Rebuild the catalog for the eff types it already has.

    Args:
        existing: The committed catalog.
        by_type: eff type -> its client SkillEff instances.

    Returns:
        The refreshed catalog, and the eff types that were dropped because the client no longer has them.
    """
    scope = set(existing) & set(by_type)
    observed = {eff_type: entry.get("observed_count", 0) for eff_type, entry in existing.items()}
    return scaffold.build_entries(by_type, scope, existing, observed), sorted(set(existing) - scope)
