"""
Recovery from a capture that ended without cleaning up.

A leftover hosts block points the game at 127.0.0.1 with nothing listening, so the game cannot
connect at all. These cover the two ways out that do not involve restarting the app.
"""

import pytest
from fastapi.testclient import TestClient

from api import state as state_mod
from api.capture import constants, manager
from api.main import app

CLEAN = "127.0.0.1 localhost\n::1 localhost\n"
BLOCK = "\n# CZN-CAPTURE-START\n127.0.0.1 live-g-czn-gamemjc2n1x.game.playstove.com\n# CZN-CAPTURE-END\n"


@pytest.fixture
def fake_hosts(tmp_path, monkeypatch):
    """Point the hosts path at a temp file and stop DNS flushes from shelling out."""
    path = tmp_path / "hosts"
    path.write_text(CLEAN + BLOCK)
    monkeypatch.setattr(constants, "HOSTS_PATH", path)
    monkeypatch.setattr(manager, "HOSTS_PATH", path)
    monkeypatch.setattr(manager, "_flush_dns", lambda: None)
    return path


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(state_mod.state, "capture_running", False)
    return TestClient(app)


def test_stop_clears_a_leftover_redirect_when_nothing_is_running(client, fake_hosts):
    # The proxy can die on its own, which sets capture_running False. Stop used to answer 409 and
    # leave the redirect in place, so the only way to get the game working again was restarting.
    res = client.post("/api/capture/stop")

    assert res.status_code == 200
    assert res.json()["hosts_restored"] is True
    assert "CZN-CAPTURE" not in fake_hosts.read_text()


def test_stop_still_reports_409_when_there_is_nothing_to_undo(client, fake_hosts):
    fake_hosts.write_text(CLEAN)
    res = client.post("/api/capture/stop")
    assert res.status_code == 409


def test_watchdog_removes_the_redirect_when_the_proxy_dies(fake_hosts, monkeypatch):
    # The proxy stopping on its own must take the redirect with it.
    from api.routes.capture import handle_proxy_death
    monkeypatch.setattr(state_mod.state, "capture_running", True)

    assert handle_proxy_death() is True

    assert state_mod.state.capture_running is False
    assert "CZN-CAPTURE" not in fake_hosts.read_text()
    assert "127.0.0.1 localhost" in fake_hosts.read_text()


def test_watchdog_does_nothing_when_capture_was_stopped_normally(fake_hosts, monkeypatch):
    # stop_capture already cleaned up and cleared the flag, so the watchdog must not fire again.
    from api.routes.capture import handle_proxy_death
    monkeypatch.setattr(state_mod.state, "capture_running", False)
    assert handle_proxy_death() is False
