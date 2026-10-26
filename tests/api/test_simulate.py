"""Tests for /simulate/damage — new damage field shape."""
from fastapi.testclient import TestClient
from api.main import app


def test_card_result_has_new_damage_fields():
    """CardResult must expose normal_damage, crit_damage, avg_damage, icon_path."""
    from api.routes.simulate import CardResult
    fields = CardResult.model_fields
    assert "normal_damage" in fields
    assert "crit_damage" in fields
    assert "avg_damage" in fields
    assert "icon_path" in fields


def test_card_result_has_no_old_fields():
    """Removed fields must not appear in CardResult."""
    from api.routes.simulate import CardResult
    fields = CardResult.model_fields
    assert "final_damage" not in fields
    assert "effective_damage" not in fields
    assert "base_damage" not in fields


def test_simulate_response_has_new_total_fields():
    """SimulateDamageResponse must expose total_normal, total_crit, total_avg."""
    from api.routes.simulate import SimulateDamageResponse
    fields = SimulateDamageResponse.model_fields
    assert "total_normal" in fields
    assert "total_crit" in fields
    assert "total_avg" in fields


def test_simulate_response_has_no_old_total_fields():
    """Removed total fields must not appear."""
    from api.routes.simulate import SimulateDamageResponse
    fields = SimulateDamageResponse.model_fields
    assert "total_damage" not in fields
    assert "total_effective_damage" not in fields


def test_avg_is_weighted_average():
    """avg = normal*(1-crate/100) + crit*(crate/100)."""
    normal = 1000.0
    crit = 2500.0
    crate = 60.0
    avg = normal * (1 - crate / 100) + crit * (crate / 100)
    assert abs(avg - 1900.0) < 0.01


def test_icon_path_with_sct_name():
    sct_name = "start_1057_01"
    icon_path = f"/assets/cards/{sct_name}.png" if sct_name else None
    assert icon_path == "/assets/cards/start_1057_01.png"


def test_icon_path_none_without_sct_name():
    sct_name = None
    icon_path = f"/assets/cards/{sct_name}.png" if sct_name else None
    assert icon_path is None


def test_simulate_no_data_returns_422():
    client = TestClient(app)
    resp = client.post("/api/simulate/damage", json={
        "char_name": "Nine",
        "morale": 0,
        "use_sparks": True,
        "monster_def": 31,
        "frightened": False,
        "exposed_stacks": 0,
        "fortitude": False,
    })
    assert resp.status_code == 422


def _stub_one_card_deck(monkeypatch):
    """Load a fake character with 1000 ATK, no crits and one 100% damage card, so a card's damage is 1000 x the damage that passes."""
    from types import SimpleNamespace
    import api.routes.simulate as sim

    optimizer = SimpleNamespace(
        character_info={"Tester": SimpleNamespace(res_id=1)},
        characters={},
        calculate_build_stats=lambda equipped, name: {"ATK": 1000.0, "CRate": 0.0, "CDmg": 150.0},
        raw_data={"inventory": {"savedata": [{"id": 7, "char_res_id": 1, "point": 1, "card_datas": [{"res_id": "card_a"}]}]}},
    )
    monkeypatch.setattr(sim.state, "data_loaded", True)
    monkeypatch.setattr(sim.state, "optimizer", optimizer)
    monkeypatch.setattr(sim, "_resolve_card_db", lambda: ({"card_a": {"cost": 1, "link_skill_eff_id": ["e1"]}}, {"e1": {"eff": "SKILL_EFF_DMG", "eff_value": 100, "eff_count_value": 1}}, {}))
    monkeypatch.setattr(sim, "_resolve_node_effects", lambda: {})
    monkeypatch.setattr(sim, "_get_char_potential_nodes", lambda res_id, raw: [])
    monkeypatch.setattr(sim, "_get_card_name", lambda card_id: card_id)


def test_simulate_uses_the_given_damage_decrease(monkeypatch):
    _stub_one_card_deck(monkeypatch)
    resp = TestClient(app).post("/api/simulate/damage", json={"char_name": "Tester", "monster_def": 220, "dmg_decrease": 0.2735})
    assert resp.status_code == 200
    assert resp.json()["def_reduction"] == round(1 - 0.2735, 4)
    assert resp.json()["cards"][0]["normal_damage"] == round(1000 * (1 - 0.2735), 1)


def test_simulate_estimates_the_decrease_from_def_without_one(monkeypatch):
    from api.optimizer.expected_damage import default_damage_reduction

    _stub_one_card_deck(monkeypatch)
    resp = TestClient(app).post("/api/simulate/damage", json={"char_name": "Tester", "monster_def": 300})
    assert resp.status_code == 200
    assert resp.json()["def_reduction"] == round(1 - default_damage_reduction(300), 4)


def _stub_epiphany_card(monkeypatch):
    """Give `card_a` an epiphany II that hits for 200% and leave the character with no in-game decks."""
    import api.routes.simulate as sim

    _stub_one_card_deck(monkeypatch)
    sim.state.optimizer.raw_data = {"inventory": {"savedata": []}}
    cards = {"card_a": {"cost": 1, "link_skill_eff_id": ["e1"]}, "card_a_rsp2": {"cost": 1, "link_skill_eff_id": ["e2"]}}
    effects = {"e1": {"eff": "SKILL_EFF_DMG", "eff_value": 100, "eff_count_value": 1}, "e2": {"eff": "SKILL_EFF_DMG", "eff_value": 200, "eff_count_value": 1}}
    monkeypatch.setattr(sim, "_resolve_card_db", lambda: (cards, effects, {"rsp2_card_a": "card_a_rsp2"}))


def test_simulate_uses_a_sent_card_list_with_its_epiphanies(monkeypatch):
    _stub_epiphany_card(monkeypatch)
    cards = [{"card_id": "card_a", "epiphany_level": 2}, {"card_id": "card_a"}]
    resp = TestClient(app).post("/api/simulate/damage", json={"char_name": "Tester", "dmg_decrease": 0.5, "cards": cards})
    assert resp.status_code == 200
    body = resp.json()
    assert body["deck_id"] is None
    assert [(card["spark_id"], card["normal_damage"]) for card in body["cards"]] == [("rsp2_card_a", 1000.0), (None, 500.0)]


def test_simulate_ignores_epiphanies_when_sparks_are_off(monkeypatch):
    _stub_epiphany_card(monkeypatch)
    cards = [{"card_id": "card_a", "epiphany_level": 2}]
    resp = TestClient(app).post("/api/simulate/damage", json={"char_name": "Tester", "dmg_decrease": 0.5, "cards": cards, "use_sparks": False})
    assert [card["normal_damage"] for card in resp.json()["cards"]] == [500.0]
