"""
Every generated data file matches what the extracted client produces.

This is the drift check for the generators: after the game updates and the client is re-extracted, it fails until
`python -m scripts.datagen` has been run and its output committed. Skips when no client is extracted, like the other
client-dependent tests. Guides are left out because they come from the network.
"""

from __future__ import annotations

import pytest

from api.client_db import client_output_dir, have_client_db, have_client_text
from scripts.datagen.runner import REPO_ROOT, Context, run
from scripts.datagen.targets import OFFLINE_TARGETS

pytestmark = pytest.mark.skipif(not (have_client_db() and have_client_text()), reason="game client DB or its text catalogue not available")


@pytest.fixture(scope="module")
def reports():
    return run(OFFLINE_TARGETS, Context(client_output_dir()), check=True)


@pytest.mark.parametrize("target", [target.NAME for target in OFFLINE_TARGETS])
def test_target_is_up_to_date(reports, target):
    report = next(report for report in reports if report.name == target)
    errors = [issue.message for issue in report.issues if issue.level == "error"]
    assert not errors, f"{target} reported errors: {errors}"
    stale = [str(path.relative_to(REPO_ROOT)) for path in report.changed]
    assert not stale, f"{target} is stale, run `python -m scripts.datagen {target}`: {stale}"
