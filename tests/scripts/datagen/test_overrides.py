"""
Tests for overrides files: filtering, applying, directives and validation.
"""

from __future__ import annotations

import json

from scripts.datagen.overrides import Overrides


def _write(tmp_path, data: dict):
    (tmp_path / "items.json").write_text(json.dumps(data), encoding="utf-8")
    return Overrides.load("items", tmp_path)


def test_a_missing_file_is_empty(tmp_path):
    overrides = Overrides.load("nothing", tmp_path)
    assert overrides.entries == {} and overrides.keeps("anything")


def test_exclude_and_include_patterns(tmp_path):
    overrides = _write(tmp_path, {"_exclude": ["eq_tut_*"], "_include": ["eq_*"]})
    assert overrides.keeps("eq_pub_001")
    assert not overrides.keeps("eq_tut_001")
    assert not overrides.keeps("relic_001")


def test_underscore_keys_are_directives_not_entries(tmp_path):
    overrides = _write(tmp_path, {"_about": "x", "_ids": {"n_0001": "card_a"}, "a": {"name": "A", "_why": "test"}})
    assert set(overrides.entries) == {"a"}
    assert overrides.directives["_ids"] == {"n_0001": "card_a"}


def test_apply_merges_fields_without_the_why(tmp_path):
    overrides = _write(tmp_path, {"a": {"name": "Fixed", "_why": "typo in client"}})
    assert overrides.apply({"a": {"name": "Broken", "cost": 1}, "b": {"name": "B"}}) == {"a": {"name": "Fixed", "cost": 1}, "b": {"name": "B"}}


def test_value_reads_one_field(tmp_path):
    overrides = _write(tmp_path, {"a": {"description": "X", "_why": "test"}})
    assert overrides.value("a", "description") == "X"
    assert overrides.value("b", "description", "default") == "default"


def test_validate_errors_and_warnings(tmp_path):
    overrides = _write(tmp_path, {
        "no_why": {"name": "A"},
        "gone": {"name": "B", "_why": "test"},
        "same": {"name": "Same", "_why": "test"},
        "real": {"name": "New", "_why": "test"},
    })
    issues = overrides.validate({"no_why": {}, "same": {"name": "Same"}, "real": {"name": "Old"}})
    by_level = {(issue.level, issue.message.split("'")[1]) for issue in issues}
    assert by_level == {("error", "no_why"), ("error", "gone"), ("warning", "same")}


def test_validate_skips_unknown_ids_when_overrides_feed_generation(tmp_path):
    overrides = _write(tmp_path, {"TALENT_X": {"title": "X", "_why": "client has no title"}})
    assert overrides.validate({}, keyed_by_output=False) == []
