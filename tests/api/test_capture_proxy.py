import socket
import threading

import pytest

from api.capture import manager
from api.capture.addon import Addon

PORT = 18801

pytest.importorskip("mitmproxy", reason="mitmproxy is a runtime dependency of the sidecar")


@pytest.fixture
def isolated_confdir(tmp_path, monkeypatch):
    """Keep mitmproxy's generated CA inside tmp_path instead of the real ~/.mitmproxy."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def test_proxy_runs_in_process_and_shuts_down(tmp_path, monkeypatch, isolated_confdir):
    # The whole point of Chunk B: no mitmdump.exe subprocess, no generated addon script.
    monkeypatch.setattr(manager, "PROXY_PORT", PORT)

    mgr = manager.CaptureManager(output_folder=tmp_path, log_callback=lambda *a, **k: None)
    mgr.addon = Addon(tmp_path)

    thread = threading.Thread(target=mgr._run_proxy, args=("127.0.0.1",), daemon=True)
    thread.start()
    try:
        assert mgr._proxy_ready.wait(timeout=30), "proxy never signalled that it started"
        assert mgr._master is not None, "DumpMaster was not created"
        assert _port_is_listening(PORT), f"nothing is listening on {PORT}"
    finally:
        if mgr._master:
            mgr._master.shutdown()
        thread.join(timeout=20)

    assert not thread.is_alive(), "proxy thread did not exit after shutdown"


def test_addon_is_a_real_module_not_a_generated_script(tmp_path):
    # It used to be a 560-line string written to disk at capture time, which meant it could not be
    # imported or tested. Editing api/capture/addon.py used to have no effect at all.
    addon = Addon(tmp_path)
    assert hasattr(addon, "websocket_message")
    assert manager.Addon is Addon
    assert not hasattr(manager, "ADDON_TEMPLATE")
    assert not hasattr(manager.CaptureManager, "_generate_addon_script")


def test_addon_reports_saves_through_the_callback(tmp_path):
    # Progress used to be discovered by scraping "Saved:" out of mitmdump's stdout.
    seen = []
    addon = Addon(tmp_path, on_saved=lambda: seen.append(1))
    addon.inventory_data = {"piece_items": [{"id": 1}]}
    addon._save_data()
    assert seen == [1]
    assert list(tmp_path.glob("memory_fragments_*.json"))


def test_certificate_is_generated_in_process(isolated_confdir):
    # setup_certificate used to spawn mitmdump and sleep 3 seconds.
    from api.capture.setup import setup_certificate, certificate_path
    path = setup_certificate()
    assert path.exists()
    assert path == certificate_path()
    assert path.parent.name == ".mitmproxy"
