"""
The CA is trusted only while capture is running.

Adding a root CA to the per-user store always shows a Windows consent dialog, so capture uses the
machine store instead - silent, because the sidecar is already elevated. The trade is a wider store
for a much shorter window, which only holds if the trust reliably comes back out again.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from api.capture import setup as capture_setup


@pytest.fixture
def cert(tmp_path):
    path = tmp_path / "mitmproxy-ca-cert.cer"
    path.write_text("not a real certificate")
    return path


@pytest.fixture
def certutil_calls(monkeypatch):
    """Record certutil invocations instead of running them."""
    calls = []

    def fake(args, timeout=15, interactive=False):
        calls.append({"args": args, "interactive": interactive})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(capture_setup, "_run_certutil", fake)
    monkeypatch.setattr(capture_setup, "get_certificate_thumbprint", lambda p: "AABBCC")
    return calls


def test_capture_install_targets_the_machine_store(cert, certutil_calls):
    capture_setup.install_certificate_for_capture(cert)
    args = certutil_calls[0]["args"]
    assert "-user" not in args, "capture must not use the per-user store"
    assert args[:3] == ["-addstore", "-f", "Root"]


def test_capture_install_never_opens_a_console_window(cert, certutil_calls):
    # A visible prompt is not expected for the machine store while elevated. If one ever did appear
    # it would be hidden and certutil would hang, so the timeout is what protects us, not a window.
    capture_setup.install_certificate_for_capture(cert)
    assert certutil_calls[0]["interactive"] is False


def test_capture_removal_leaves_the_per_user_store_alone(cert, certutil_calls):
    assert capture_setup.remove_capture_certificate(cert) is True
    assert len(certutil_calls) == 1
    assert certutil_calls[0]["args"] == ["-delstore", "Root", "AABBCC"]


def test_install_clears_the_machine_store_memo(cert, certutil_calls):
    # is_certificate_trusted caches machine-store misses. That was safe when the store never changed
    # mid-run, but capture changes it now, so a stale memo would report the CA as untrusted.
    capture_setup._machine_store_misses.add("AABBCC")
    capture_setup.install_certificate_for_capture(cert)
    assert "AABBCC" not in capture_setup._machine_store_misses


def test_removal_clears_the_machine_store_memo(cert, certutil_calls):
    capture_setup._machine_store_misses.add("AABBCC")
    capture_setup.remove_capture_certificate(cert)
    assert "AABBCC" not in capture_setup._machine_store_misses


def test_install_fails_loudly_when_the_certificate_file_is_missing(tmp_path):
    with pytest.raises(capture_setup.CertificateInstallError):
        capture_setup.install_certificate_for_capture(tmp_path / "nope.cer")


def test_removal_reports_false_when_there_was_nothing_to_remove(cert, monkeypatch):
    monkeypatch.setattr(capture_setup, "_run_certutil",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="not found"))
    assert capture_setup.remove_capture_certificate(cert) is False


def test_setup_install_still_uses_the_per_user_store(cert, certutil_calls):
    # The manual Setup button is unchanged: it is the user's own permanent choice, and per-user is
    # the narrower store for something that outlives a capture.
    capture_setup.install_certificate(cert)
    assert certutil_calls[0]["args"][0] == "-user"
    assert certutil_calls[0]["interactive"] is True


def test_trust_answer_is_cached_between_polls(cert, monkeypatch):
    # Setup and Capture both poll the status endpoint, so this used to spawn certutil every few
    # seconds. The answer is held briefly instead.
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(capture_setup, "get_certificate_thumbprint", lambda p: "AABBCC")
    monkeypatch.setattr(capture_setup, "_run_certutil",
                        lambda *a, **k: calls.append(1) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    capture_setup._trust_cache.clear()

    assert capture_setup.is_certificate_trusted(cert) is True
    assert capture_setup.is_certificate_trusted(cert) is True
    assert capture_setup.is_certificate_trusted(cert) is True

    assert len(calls) == 1, "certutil should only run once for repeated polls"


def test_installing_for_capture_invalidates_the_cache(cert, certutil_calls):
    # Capture changes trust mid-run, so a cached "not trusted" must not survive it.
    capture_setup._trust_cache["AABBCC"] = (False, 9e9)
    capture_setup.install_certificate_for_capture(cert)
    assert "AABBCC" not in capture_setup._trust_cache


def test_removing_for_capture_invalidates_the_cache(cert, certutil_calls):
    capture_setup._trust_cache["AABBCC"] = (True, 9e9)
    capture_setup.remove_capture_certificate(cert)
    assert "AABBCC" not in capture_setup._trust_cache


def test_expiry_is_read_from_the_certificate(tmp_path):
    from api.capture.setup import certificate_expiry, certificate_days_left, certificate_path
    real = certificate_path()
    if not real.exists():
        import pytest as _pytest
        _pytest.skip("no CA generated on this machine")
    assert certificate_expiry(real) is not None
    assert certificate_days_left(real) == (certificate_expiry(real) - __import__("datetime").datetime.now(__import__("datetime").timezone.utc)).days


def test_expiry_of_a_missing_certificate_is_none(tmp_path):
    from api.capture.setup import certificate_expiry, certificate_days_left
    missing = tmp_path / "nope.cer"
    assert certificate_expiry(missing) is None
    assert certificate_days_left(missing) is None


def test_expiry_of_an_unparseable_file_is_none(cert):
    from api.capture.setup import certificate_expiry
    assert certificate_expiry(cert) is None
