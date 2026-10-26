# tests/api/test_capture_autostart.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.capture import settings as capture_settings
from api.main import app
from api.routes import capture as capture_routes
from api.state import state

client = TestClient(app)


def _patched(mgr, admin=True):
    return (
        patch("api.routes.capture._is_admin", return_value=admin),
        patch("api.state.AppState.get_capture_manager", return_value=mgr),
        patch("threading.Thread"),
    )


def test_settings_default_off():
    assert capture_settings.load_capture_settings()["auto_start"] is False
    r = client.get("/api/capture/settings")
    assert r.status_code == 200
    assert r.json()["auto_start"] is False


def test_settings_round_trip():
    r = client.post("/api/capture/settings", json={"auto_start": True})
    assert r.status_code == 200
    assert r.json()["auto_start"] is True
    assert capture_settings.load_capture_settings()["auto_start"] is True


def test_settings_corrupt_file_falls_back_to_defaults():
    capture_settings.SETTINGS_PATH.write_text("{not json", encoding="utf-8")
    assert capture_settings.load_capture_settings()["auto_start"] is False


def test_set_region_is_remembered_for_auto_start():
    client.post("/api/capture/set-region", json={"region": "asia"})
    assert capture_settings.load_capture_settings()["region"] == "asia"


def test_auto_start_does_nothing_when_off():
    mgr = MagicMock()
    a, b, c = _patched(mgr)
    with a, b, c:
        assert capture_routes.auto_start_capture() is False
    mgr.start_capture.assert_not_called()
    assert state.capture_running is False


def test_auto_start_starts_capture_with_saved_region():
    capture_settings.save_capture_settings({"auto_start": True, "region": "asia"})
    mgr = MagicMock()
    a, b, c = _patched(mgr)
    with a, b, c:
        assert capture_routes.auto_start_capture() is True
    mgr.set_region.assert_called_once_with("asia")
    mgr.start_capture.assert_called_once_with(debug_mode=False)
    assert state.capture_running is True
    assert state.capture_auto_started is True
    assert any("automatically" in e["message"] for e in state.log_tail)
    state.capture_running = False
    state.reset_capture_manager()


def test_auto_start_skips_without_admin():
    capture_settings.save_capture_settings({"auto_start": True, "region": "global"})
    mgr = MagicMock()
    a, b, c = _patched(mgr, admin=False)
    with a, b, c:
        assert capture_routes.auto_start_capture() is False
    mgr.start_capture.assert_not_called()


def test_auto_start_failure_is_logged_not_raised():
    capture_settings.save_capture_settings({"auto_start": True, "region": "global"})
    mgr = MagicMock()
    mgr.start_capture.side_effect = RuntimeError("no network")
    a, b, c = _patched(mgr)
    with a, b, c:
        assert capture_routes.auto_start_capture() is False
    assert state.capture_running is False
    assert state.capture_auto_started is False
    assert any(e["level"] == "error" and "no network" in e["message"] for e in state.log_tail)


def test_manual_start_is_not_flagged_auto():
    mgr = MagicMock()
    a, b, c = _patched(mgr)
    with a, b, c:
        client.post("/api/capture/start", json={"region": "global", "debug": False})
    assert state.capture_auto_started is False
    assert client.get("/api/capture/status").json()["auto_started"] is False
    state.capture_running = False
    state.reset_capture_manager()


def test_stop_clears_auto_started_flag():
    state.capture_running = True
    state.capture_auto_started = True
    mgr = MagicMock()
    mgr.stop_capture.return_value = None
    with patch("api.state.AppState.get_capture_manager", return_value=mgr):
        client.post("/api/capture/stop")
    assert state.capture_auto_started is False
