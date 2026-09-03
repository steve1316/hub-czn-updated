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


def test_setup_status_reports_a_stuck_redirect(client, fake_hosts):
    # Setup polls this, so a leftover block becomes visible instead of silently breaking the game.
    res = client.get("/api/setup/status")
    assert res.status_code == 200
    assert res.json()["hosts_redirect_active"] is True


def test_setup_status_is_quiet_when_the_hosts_file_is_clean(client, fake_hosts):
    fake_hosts.write_text(CLEAN)
    assert client.get("/api/setup/status").json()["hosts_redirect_active"] is False


def test_setup_status_never_writes_to_the_hosts_file(client, fake_hosts):
    before = fake_hosts.read_text()
    mtime = fake_hosts.stat().st_mtime_ns
    client.get("/api/setup/status")
    assert fake_hosts.read_text() == before
    assert fake_hosts.stat().st_mtime_ns == mtime


def test_clear_redirect_removes_the_block(client, fake_hosts):
    res = client.post("/api/setup/clear-redirect")
    assert res.status_code == 200
    assert res.json() == {"ok": True, "removed": True}
    assert "CZN-CAPTURE" not in fake_hosts.read_text()


def test_clear_redirect_is_harmless_when_there_is_nothing_to_remove(client, fake_hosts):
    fake_hosts.write_text(CLEAN)
    assert client.post("/api/setup/clear-redirect").json() == {"ok": True, "removed": False}
    assert fake_hosts.read_text() == CLEAN


def test_a_deliberate_stop_is_not_reported_as_a_crash(client, fake_hosts, monkeypatch):
    # The watchdog wakes as soon as the proxy shuts down. If the running flag is still set by then
    # it logs "stopped unexpectedly" on every normal stop, which is alarming and wrong.
    from api.routes.capture import handle_proxy_death

    seen = []

    class FakeManager:
        def stop_capture(self):
            # Stands in for the watchdog waking mid-shutdown.
            seen.append(handle_proxy_death())
            return None

    monkeypatch.setattr(state_mod.state, "capture_running", True)
    monkeypatch.setattr(state_mod.state, "get_capture_manager", lambda: FakeManager())
    monkeypatch.setattr(state_mod.state, "reset_capture_manager", lambda: None)

    client.post("/api/capture/stop")

    assert seen == [False], "watchdog fired during a deliberate stop"
