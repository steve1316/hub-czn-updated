"""
Deliberate deviations from the generated data, kept in one reviewable file per target.

A file lives at `api/data/overrides/<target>.json`:

    {
      "_exclude": ["eq_dpt_test_*"],
      "eq_pub_021": {"image_path": "itens/item_0021.webp", "_why": "client icon not extracted"}
    }

Keys starting with an underscore are directives rather than output ids. `_exclude` and `_include` filter source ids by
glob pattern before generation, `_about` explains the file, and a target may define its own (such as `_ids`). Every other
key is an output id whose fields replace the generated ones, and must say why in `_why`. Validation reports an override
for an id that no longer exists as an error, and one that changes nothing as a warning, so dead entries get removed
instead of piling up.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path

from api.client_db import REPO_ROOT

OVERRIDES_DIR = REPO_ROOT / "api" / "data" / "overrides"

# Keys starting with this are directives rather than output ids.
_DIRECTIVE_PREFIX = "_"


@dataclass(frozen=True)
class Issue:
    """One problem found while validating an overrides file."""

    # "error" fails `--check`. "warning" is printed but does not.
    level: str
    # What is wrong, naming the target and id.
    message: str


@dataclass
class Overrides:
    """The overrides for one target."""

    # The target name, such as "items". Used in messages.
    target: str
    # Output id -> fields to replace, each including its `_why`.
    entries: dict[str, dict] = field(default_factory=dict)
    # Glob patterns of source ids to drop.
    exclude: list[str] = field(default_factory=list)
    # Glob patterns of source ids to keep. Empty means keep everything not excluded.
    include: list[str] = field(default_factory=list)
    # Every underscore-prefixed key in the file, as written, for directives a target defines itself.
    directives: dict = field(default_factory=dict)

    @classmethod
    def load(cls, target: str, directory: Path = OVERRIDES_DIR) -> "Overrides":
        """
        Read a target's overrides file.

        Args:
            target: The target name. The file is `<directory>/<target>.json`.
            directory: Where overrides files live.

        Returns:
            The overrides, empty when the target has no file.
        """
        path = directory / f"{target}.json"
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        entries = {key: value for key, value in raw.items() if not key.startswith(_DIRECTIVE_PREFIX)}
        directives = {key: value for key, value in raw.items() if key.startswith(_DIRECTIVE_PREFIX)}
        return cls(target, entries, list(raw.get("_exclude", [])), list(raw.get("_include", [])), directives)

    def keeps(self, source_id: str) -> bool:
        """
        Whether a source row survives the `_include` and `_exclude` filters.

        Args:
            source_id: The row's id in the client.

        Returns:
            False when it matches an exclude pattern, or include patterns exist and it matches none of them.
        """
        if any(fnmatch.fnmatchcase(source_id, pattern) for pattern in self.exclude):
            return False
        return not self.include or any(fnmatch.fnmatchcase(source_id, pattern) for pattern in self.include)

    def value(self, entry_id: str, field_name: str, default=None):
        """
        One overridden field, for overrides that feed generation rather than replace output.

        Args:
            entry_id: The override key.
            field_name: The field inside that entry.
            default: Returned when there is no such override.

        Returns:
            The overridden value, or `default`.
        """
        return self.entries.get(entry_id, {}).get(field_name, default)

    def unresolved(self, entry_id: str, label: str, placeholders: list[str], field_name: str | None = None) -> list[Issue]:
        """
        Report placeholders a template could not fill, unless an override replaces what they were in.

        Args:
            entry_id: The output id an override would be keyed by.
            label: How the message names the entry, such as "c_1008_srt4" or "card_a (n_0001)".
            placeholders: The unresolved placeholders.
            field_name: The overridden field that silences the report. None means any override of the entry does.

        Returns:
            One error naming the placeholders, or nothing when there are none or the override covers them.
        """
        if not placeholders:
            return []
        entry = self.entries.get(entry_id)
        if entry is not None and (field_name is None or field_name in entry):
            return []
        return [Issue("error", f"{self.target}: {label} has unresolved placeholders {placeholders}")]

    def apply(self, generated: dict[str, dict]) -> dict[str, dict]:
        """
        Replace generated fields with overridden ones.

        Args:
            generated: Output id -> generated entry.

        Returns:
            A new mapping with each override's fields merged over its entry. Entries without an override are unchanged.
        """
        result = dict(generated)
        for entry_id, fields in self.entries.items():
            if entry_id in result:
                result[entry_id] = {**result[entry_id], **_without_why(fields)}
        return result

    def validate(self, generated: dict[str, dict], *, keyed_by_output: bool = True) -> list[Issue]:
        """
        Check the overrides against what was generated.

        Args:
            generated: Output id -> entry, before overrides were applied.
            keyed_by_output: False for targets whose overrides feed generation (such as talent titles) instead of
                replacing output entries, so unknown ids are not an error there.

        Returns:
            Errors for entries without a `_why` and for ids that are not in the output, and warnings for entries whose
            fields already equal the generated ones.
        """
        issues = []
        for entry_id, fields in self.entries.items():
            if not isinstance(fields, dict) or not str(fields.get("_why", "")).strip():
                issues.append(Issue("error", f"{self.target}: override '{entry_id}' has no _why"))
                continue
            if not keyed_by_output:
                continue
            if entry_id not in generated:
                issues.append(Issue("error", f"{self.target}: override '{entry_id}' matches nothing in the generated output"))
            elif all(generated[entry_id].get(key) == value for key, value in _without_why(fields).items()):
                issues.append(Issue("warning", f"{self.target}: override '{entry_id}' changes nothing and can be removed"))
        return issues


def _without_why(fields: dict) -> dict:
    """The override's fields with its `_why` note removed."""
    return {key: value for key, value in fields.items() if key != "_why"}
