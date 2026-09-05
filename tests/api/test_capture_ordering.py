# tests/api/test_capture_ordering.py
"""
Two ordering bugs in the capture lifecycle.

Both concern the window in which the hosts redirect is live: one where it poisons the address the
proxy forwards to, one where it points the game at a port nothing is listening on.
"""
from unittest import mock

import pytest

from api.capture.manager import CaptureManager, CaptureError


HOST = "live-g-czn-gamemjc2n1x.game.playstove.com"
REAL_IP = "166.117.38.100"


@pytest.fixture
def mgr(tmp_path):
    return CaptureManager(output_folder=tmp_path, log_callback=lambda *a, **k: None)


# ---- resolve_game_server resolving through its own redirect ----------

def test_resolve_rejects_a_loopback_answer(mgr):
    # modify_hosts_file() returns early and unchanged when the CZN block is already present, so a
    # start that follows a stale block from a crashed run resolves the game host *through* that
    # redirect. The 127.0.0.1 it gets back then becomes the reverse proxy's upstream, and the
    # proxy forwards to itself.
    with mock.patch("socket.gethostbyname", return_value="127.0.0.1"):
        with pytest.raises(CaptureError) as exc:
            mgr.resolve_game_server()
    assert "hosts" in str(exc.value).lower()


def test_the_loopback_error_says_how_to_fix_it(mgr):
    with mock.patch("socket.gethostbyname", return_value="127.0.0.1"):
        with pytest.raises(CaptureError) as exc:
            mgr.resolve_game_server()
    assert "setup" in str(exc.value).lower()


def test_any_loopback_address_counts_not_just_127_0_0_1(mgr):
    with mock.patch("socket.gethostbyname", return_value="127.1.2.3"):
        with pytest.raises(CaptureError):
            mgr.resolve_game_server()


def test_resolve_keeps_a_real_answer(mgr):
    with mock.patch("socket.gethostbyname", return_value=REAL_IP):
        mgr.resolve_game_server()
    assert mgr.game_server_ips == {HOST: REAL_IP}


def test_resolve_ignores_hosts_that_do_not_resolve(mgr):
    import socket as s
    with mock.patch("socket.gethostbyname", side_effect=s.gaierror):
        mgr.resolve_game_server()
    assert mgr.game_server_ips == {}


# ---- stop_capture taking the listener down before the redirect -------

def test_stop_removes_the_redirect_before_stopping_the_proxy(mgr):
    # Between master.shutdown() and restore_hosts_file() the hosts entry still sends the game to
    # 127.0.0.1 while nothing is listening there, so a game reconnecting in that window hits a
    # closed port instead of the real server. Undo the redirect first, then take the listener down.
    order = []
    mgr.capturing = True
    mgr._master = mock.Mock(shutdown=lambda: order.append("shutdown"))
    with mock.patch.object(CaptureManager, "restore_hosts_file",
                           lambda self: order.append("restore_hosts")), \
         mock.patch.object(CaptureManager, "_untrust_certificate", lambda self: None):
        mgr.stop_capture()
    assert order == ["restore_hosts", "shutdown"]


def test_stop_still_untrusts_the_certificate_and_clears_the_flag(mgr):
    calls = []
    mgr.capturing = True
    mgr._master = mock.Mock(shutdown=lambda: None)
    with mock.patch.object(CaptureManager, "restore_hosts_file", lambda self: None), \
         mock.patch.object(CaptureManager, "_untrust_certificate",
                           lambda self: calls.append("untrust")):
        mgr.stop_capture()
    assert calls == ["untrust"]
    assert mgr.capturing is False
    assert mgr.addon is None


def test_stop_does_nothing_when_not_capturing(mgr):
    with mock.patch.object(CaptureManager, "restore_hosts_file") as restore:
        assert mgr.stop_capture() is None
    restore.assert_not_called()
