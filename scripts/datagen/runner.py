"""
Run generators, then write their output or compare it with what is on disk.

A target returns the full content it wants for each file. The runner writes a file only when that content differs, so a
run over unchanged client data touches nothing, and in `--check` mode it writes nothing and reports what would change.
"""

from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from types import ModuleType

from api.client_db import REPO_ROOT
from scripts.datagen.client import Client
from scripts.datagen.overrides import Issue, Overrides
from scripts.datagen.templates import TemplateResolver
from scripts.datagen.tidy import TidyRules, tidy

# Files compared as text, where a CRLF working copy must not count as a change. Everything else is compared byte for byte.
_TEXT_SUFFIXES = (".json", ".py", ".ts", ".md", ".txt")


@dataclass
class TargetResult:
    """What one target wants on disk."""

    # Repo-relative or absolute path -> the full content wanted there.
    files: dict[Path, bytes] = field(default_factory=dict)
    # One line describing the content, such as "38 characters, 12 cards updated".
    summary: str = ""
    # Problems the target found, such as unresolved placeholders or invalid overrides.
    issues: list[Issue] = field(default_factory=list)
    # Files created only when missing (or when art is refreshed), alongside the normal `files`. Used for images.
    new_files: dict[Path, bytes] = field(default_factory=dict)


@dataclass
class TargetReport:
    """What happened to one target in a run."""

    # The target name.
    name: str
    # The target's own summary line.
    summary: str = ""
    # Paths whose content differs from what is on disk (or that are missing).
    changed: list[Path] = field(default_factory=list)
    # Issues from the target, plus a crash if it raised.
    issues: list[Issue] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """True when any issue is an error."""
        return any(issue.level == "error" for issue in self.issues)


class Context:
    """Shared inputs for every target in a run."""

    def __init__(self, client_root: Path, *, refresh_art: bool = False):
        """
        Args:
            client_root: The extracted client folder.
            refresh_art: Re-encode existing images instead of only adding missing ones.
        """
        self.client = Client(client_root)
        self.refresh_art = refresh_art
        self.rules = TidyRules.load()
        self._overrides: dict[str, Overrides] = {}

    def overrides(self, target: str) -> Overrides:
        """
        A target's overrides, read once per run.

        Args:
            target: The target name.

        Returns:
            Its overrides, empty when it has no file.
        """
        if target not in self._overrides:
            self._overrides[target] = Overrides.load(target)
        return self._overrides[target]

    @cached_property
    def resolver(self) -> TemplateResolver:
        """The template resolver, with trait titles the client lacks taken from the `templates` overrides."""
        titles = {talent: fields["title"] for talent, fields in self.overrides("templates").entries.items() if "title" in fields}
        return TemplateResolver(self.client, titles)

    def text(self, raw: str, *, soften: bool = False, sentences: bool = True, keep_lines: bool = False) -> str:
        """
        Run resolved text through the tidy pass.

        Args:
            raw: Resolved text, lines separated by "\n".
            soften: Apply the swear-softening list.
            sentences: Join lines into sentences ending with a period.
            keep_lines: Keep each sentence on its own line.

        Returns:
            The tidied text.
        """
        return tidy(raw, self.rules, soften=soften, sentences=sentences, keep_lines=keep_lines)


def json_bytes(data) -> bytes:
    """
    Serialise data the way every generated JSON file is written.

    Args:
        data: Any JSON-compatible value.

    Returns:
        UTF-8 JSON with a two-space indent and a trailing newline.
    """
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def replace_literal(module: str, name: str, source: str, path: Path) -> str:
    """
    Swap one top-level dict literal in a module, from its opening line to the closing brace on its own line.

    Args:
        module: The module source.
        name: The literal's name. A type annotation after it is allowed.
        source: The new assignment, ending with a newline.
        path: The module's path, for the error message.

    Returns:
        The module with the literal replaced.

    Raises:
        ValueError: When the literal is not in the module.
    """
    block = re.compile(rf"^{re.escape(name)}(?::[^=\n]*)? = \{{\n.*?^\}}\n", re.DOTALL | re.MULTILINE)
    if not block.search(module):
        raise ValueError(f"could not find the {name} table in {path}")
    return block.sub(lambda _: source, module, count=1)


def run(targets: list[ModuleType], context: Context, *, check: bool) -> list[TargetReport]:
    """
    Build each target, then write or compare its files.

    A target that raises is reported as failed and the run carries on with the rest, so one broken generator does not
    stop the others from refreshing.

    Args:
        targets: Target modules, each exposing `NAME` and `build(context) -> TargetResult`.
        context: The shared inputs.
        check: Compare only. Nothing is written.

    Returns:
        One report per target, in order.
    """
    reports = []
    for target in targets:
        report = TargetReport(target.NAME)
        try:
            result = target.build(context)
        except Exception as exc:  # noqa: BLE001 - one target's crash must not stop the others
            report.issues.append(Issue("error", f"{target.NAME}: crashed: {exc}\n{traceback.format_exc()}"))
            reports.append(report)
            continue
        report.summary = result.summary
        report.issues.extend(result.issues)
        # Joining onto REPO_ROOT leaves an absolute path as it is.
        new_files = {path: content for path, content in result.new_files.items() if context.refresh_art or not (REPO_ROOT / path).exists()}
        for path, content in [*result.files.items(), *new_files.items()]:
            path = REPO_ROOT / path
            if _differs(path, content):
                report.changed.append(path)
                if not check:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
        reports.append(report)
    return reports


def _differs(path: Path, content: bytes) -> bool:
    """
    Whether a file on disk differs from the wanted content.

    Args:
        path: The file.
        content: The wanted bytes.

    Returns:
        True when the file is missing or its content differs. Line endings are ignored for text files.
    """
    if not path.is_file():
        return True
    current = path.read_bytes()
    if path.suffix in _TEXT_SUFFIXES:
        return current.replace(b"\r\n", b"\n") != content.replace(b"\r\n", b"\n")
    return current != content
