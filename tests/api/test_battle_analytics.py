"""
Battle analytics reads the damage decrease the game reported for the enemy, and flags a low CRate with the same cutoff as the overview.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from api.optimizer.expected_damage import default_damage_reduction

client = TestClient(app)

MOCK_SNAPSHOTS = "api.routes.battle._snapshots_dir"


def _analytics(tmp_path: Path, **overrides) -> dict:
    """
    Write one battle and fetch its analytics.

    Args:
        tmp_path: The snapshots folder.
        **overrides: Fields that replace the default battle's.

    Returns:
        The analytics response body.
    """
    battle = {
        "capture_time": "2026-05-04T12:00:00",
        "enemy_def": 300.0,
        "enemy_dmg_decrease": 0.0,
        "player_chars": [{"res_id": 1060, "atk": 1000, "def": 100, "cri": 60.0, "cri_dmg": 180.0}],
    }
    battle.update(overrides)
    (tmp_path / "battle_001.json").write_text(json.dumps(battle), encoding="utf-8")
    with patch(MOCK_SNAPSHOTS, return_value=tmp_path):
        r = client.get("/api/battle/analytics")
    assert r.status_code == 200
    return r.json()


def test_def_factor_uses_the_captured_damage_decrease(tmp_path):
    body = _analytics(tmp_path, enemy_dmg_decrease=0.3262)
    assert body["def_factor"] == round(1 - 0.3262, 4)


def test_def_factor_falls_back_to_the_fitted_curve(tmp_path):
    body = _analytics(tmp_path, enemy_def=300.0)
    assert body["def_factor"] == round(1 - default_damage_reduction(300), 4)


def test_damage_per_coeff_follows_the_def_factor(tmp_path):
    body = _analytics(tmp_path, enemy_dmg_decrease=0.25)
    char = body["chars"][0]
    assert char["dmg_per_100coeff"] == round(1000 * char["crit_factor"] * 0.75, 0)


def test_low_crate_cutoff_matches_the_overview(tmp_path):
    char = {"res_id": 1060, "atk": 1000, "def": 100, "cri": 25.0, "cri_dmg": 150.0}
    body = _analytics(tmp_path, player_chars=[char])
    assert body["chars"][0]["priority"] == "crate_low"
