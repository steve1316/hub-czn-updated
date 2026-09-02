import os
import stat
import sys

import pytest

from api.capture import constants, manager, setup as capture_setup

CLEAN = "127.0.0.1 localhost\n::1 localhost\n"
WITH_BLOCK = (
    CLEAN
    + "\n# CZN-CAPTURE-START\n127.0.0.1 live-g-czn-gamemjc2n1x.game.playstove.com\n# CZN-CAPTURE-END\n"
)


@pytest.fixture
def fake_hosts(tmp_path, monkeypatch):
    """Point HOSTS_PATH at a temp file and stop DNS flushes from shelling out."""
    path = tmp_path / "hosts"
    path.write_text(CLEAN)
    monkeypatch.setattr(constants, "HOSTS_PATH", path)
    monkeypatch.setattr(manager, "HOSTS_PATH", path)
    monkeypatch.setattr(manager, "_flush_dns", lambda: None)
    return path


def test_probe_does_not_modify_the_hosts_file(fake_hosts):
    # The Setup page polls this every 5 seconds, so it must never write. A writing probe used to
    # race modify_hosts_file() and could strip a live capture's redirect.
    before = fake_hosts.read_text()
    before_mtime = fake_hosts.stat().st_mtime_ns

    ok, reason = capture_setup._probe_hosts_writable()

    assert ok is True
    assert reason is None
    assert fake_hosts.read_text() == before
    assert fake_hosts.stat().st_mtime_ns == before_mtime


def test_probe_keeps_an_existing_capture_block_intact(fake_hosts):
    fake_hosts.write_text(WITH_BLOCK)
    capture_setup._probe_hosts_writable()
    assert "CZN-CAPTURE-START" in fake_hosts.read_text()


@pytest.mark.skipif(sys.platform != "win32", reason="read-only attribute check is Windows only")
def test_probe_reports_failure_when_the_file_is_not_writable(fake_hosts):
    os.chmod(fake_hosts, stat.S_IREAD)
    try:
        ok, reason = capture_setup._probe_hosts_writable()
    finally:
        os.chmod(fake_hosts, stat.S_IWRITE | stat.S_IREAD)
    assert ok is False
    assert reason


def test_remove_capture_entries_strips_the_block(fake_hosts):
    fake_hosts.write_text(WITH_BLOCK)
    assert manager.remove_capture_entries() is True
    text = fake_hosts.read_text()
    assert "CZN-CAPTURE" not in text
    assert "127.0.0.1 localhost" in text


def test_remove_capture_entries_is_a_noop_on_a_clean_file(fake_hosts):
    before_mtime = fake_hosts.stat().st_mtime_ns
    assert manager.remove_capture_entries() is False
    assert fake_hosts.read_text() == CLEAN
    assert fake_hosts.stat().st_mtime_ns == before_mtime


def test_modify_then_restore_round_trips(fake_hosts):
    mgr = manager.CaptureManager(output_folder=fake_hosts.parent, log_callback=lambda *a, **k: None)
    mgr.set_region("global")

    mgr.modify_hosts_file()
    assert "CZN-CAPTURE-START" in fake_hosts.read_text()

    mgr.restore_hosts_file()
    assert fake_hosts.read_text() == CLEAN


def test_startup_clears_entries_left_by_a_crash(fake_hosts):
    # The Tauri Job Object kills the sidecar with no cleanup, so a crash mid-capture leaves the
    # game pointed at 127.0.0.1. Startup has to undo that.
    fake_hosts.write_text(WITH_BLOCK)
    from api.state import clear_stale_hosts_entries
    clear_stale_hosts_entries()
    assert "CZN-CAPTURE" not in fake_hosts.read_text()
