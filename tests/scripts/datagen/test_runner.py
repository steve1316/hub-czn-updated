"""
Tests for the runner: it writes only changed files, never writes in check mode, ignores line endings, adds images only
when missing, and keeps going when one target crashes.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.datagen.overrides import Issue
from scripts.datagen.runner import Context, TargetResult, json_bytes, run
from tests.scripts.datagen.fixture_client import write_client


def _target(name: str, result_or_error):
    def build(ctx):
        if isinstance(result_or_error, Exception):
            raise result_or_error
        return result_or_error
    return SimpleNamespace(NAME=name, build=build)


def _context(tmp_path, refresh_art=False):
    return Context(write_client(tmp_path / "client", {}, {}), refresh_art=refresh_art)


def test_writes_new_and_changed_files_only(tmp_path):
    same, changed, new = tmp_path / "same.json", tmp_path / "changed.json", tmp_path / "new.json"
    same.write_bytes(json_bytes({"a": 1}))
    changed.write_bytes(json_bytes({"a": 1}))
    result = TargetResult({same: json_bytes({"a": 1}), changed: json_bytes({"a": 2}), new: json_bytes({"b": 1})})
    [report] = run([_target("t", result)], _context(tmp_path), check=False)
    assert sorted(report.changed) == sorted([changed, new])
    assert changed.read_bytes() == json_bytes({"a": 2}) and new.exists()


def test_check_mode_writes_nothing(tmp_path):
    path = tmp_path / "out.json"
    [report] = run([_target("t", TargetResult({path: b"{}\n"}))], _context(tmp_path), check=True)
    assert report.changed == [path] and not path.exists()


def test_line_endings_do_not_count_as_a_change(tmp_path):
    path = tmp_path / "out.json"
    path.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')
    [report] = run([_target("t", TargetResult({path: b'{\n  "a": 1\n}\n'}))], _context(tmp_path), check=True)
    assert report.changed == []


def test_new_files_are_only_created_when_missing(tmp_path):
    existing, missing = tmp_path / "old.webp", tmp_path / "new.webp"
    existing.write_bytes(b"old")
    result = TargetResult(new_files={existing: b"re-encoded", missing: b"new"})
    [report] = run([_target("t", result)], _context(tmp_path), check=False)
    assert report.changed == [missing] and existing.read_bytes() == b"old"


def test_refresh_art_rewrites_existing_images(tmp_path):
    existing = tmp_path / "old.webp"
    existing.write_bytes(b"old")
    run([_target("t", TargetResult(new_files={existing: b"re-encoded"}))], _context(tmp_path, refresh_art=True), check=False)
    assert existing.read_bytes() == b"re-encoded"


def test_a_crash_is_reported_and_later_targets_still_run(tmp_path):
    path = tmp_path / "after.json"
    reports = run([_target("broken", RuntimeError("boom")), _target("after", TargetResult({path: b"{}\n"}))], _context(tmp_path), check=False)
    assert reports[0].failed and "boom" in reports[0].issues[0].message
    assert not reports[1].failed and path.exists()


def test_error_issues_mark_a_target_failed(tmp_path):
    [report] = run([_target("t", TargetResult(issues=[Issue("error", "bad")]))], _context(tmp_path), check=True)
    assert report.failed
