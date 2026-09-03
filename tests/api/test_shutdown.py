"""
The sidecar tidies up after itself when Tauri goes away.

Tauri no longer kills it, so this is the only thing that undoes a capture when the window is closed
or the app is force-quit mid-capture.
"""

import pytest

from api import shutdown


def test_no_watcher_without_a_parent_pid(monkeypatch):
    # Running the sidecar by hand, where there is no Tauri to watch.
    monkeypatch.delenv(shutdown.PARENT_PID_ENV, raising=False)
    assert shutdown.watch_parent() is False


@pytest.mark.parametrize("value", ["", "   ", "not-a-pid", "-1", "12.5"])
def test_junk_in_the_pid_variable_is_ignored(monkeypatch, value):
    monkeypatch.setenv(shutdown.PARENT_PID_ENV, value)
    assert shutdown.watch_parent() is False


def test_no_watcher_when_the_parent_cannot_be_opened(monkeypatch):
    # A bad handle must not start a watcher. A thread that read it as "parent died" would clean up
    # and exit while the app was still perfectly alive.
    monkeypatch.setenv(shutdown.PARENT_PID_ENV, "4294967295")
    assert shutdown.watch_parent() is False


def test_cleanup_undoes_both_halves_of_a_capture(monkeypatch):
    from api.capture import manager, setup as capture_setup
    calls = []
    monkeypatch.setattr(manager, "remove_capture_entries", lambda: calls.append("hosts") or True)
    monkeypatch.setattr(capture_setup, "remove_capture_certificate", lambda p: calls.append("cert") or True)

    shutdown.cleanup()

    assert calls == ["hosts", "cert"]


def test_cleanup_never_raises(monkeypatch):
    # It runs while the app is going away, so a failure here must not stop the process exiting.
    from api.capture import manager
    def boom():
        raise RuntimeError("hosts file locked")
    monkeypatch.setattr(manager, "remove_capture_entries", boom)

    shutdown.cleanup()
