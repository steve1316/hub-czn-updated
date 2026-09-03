# tests/api/test_setup.py
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def _cert_stub(exists: bool):
    """Stand-in for certificate_path() so the cert endpoints do not touch the real filesystem."""
    cert = MagicMock(spec=Path)
    cert.exists.return_value = exists
    return cert


def _record_runs(monkeypatch, returncodes):
    """Patch subprocess.run to record argv lists and return the given exit codes in order."""
    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd))
        rc = returncodes[len(calls) - 1] if len(calls) <= len(returncodes) else returncodes[-1]
        return subprocess.CompletedProcess(args=cmd, returncode=rc, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_setup_status_returns_expected_shape():
    mock_status = MagicMock(
        is_admin=False,
        has_mitmproxy=True,
        mitmproxy_version="10.1.1",
        has_certificate=False,
        certificate_path=None,
        certificate_trusted=False,
    )
    with patch("api.routes.setup.check_prerequisites", return_value=mock_status):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body["admin"] is False
    assert body["mitmproxy"] is True
    assert body["mitmproxy_version"] == "10.1.1"
    assert body["certificate"] is False


def test_generate_cert_success():
    from pathlib import Path
    with patch("api.routes.setup.setup_certificate", return_value=Path("/fake/cert.cer")):
        r = client.post("/api/setup/generate-cert")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_open_cert_no_certificate():
    with patch("api.routes.setup.certificate_path", return_value=_cert_stub(False)):
        r = client.post("/api/setup/open-cert")
    assert r.status_code == 404


def test_generate_cert_failure():
    with patch("api.routes.setup.setup_certificate", side_effect=Exception("mitmdump not found")):
        r = client.post("/api/setup/generate-cert")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "mitmdump not found" in body["error"]


def _write_pem_cert(tmp_path: Path) -> tuple[Path, str]:
    """Generate a self-signed cert in PEM format. Returns (path, expected_sha1_thumbprint_hex_uppercase)."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem_path = tmp_path / "test-cert.cer"
    pem_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    expected = cert.fingerprint(hashes.SHA1()).hex().upper()
    return pem_path, expected


def test_thumbprint_matches_known_pem_cert(tmp_path):
    from api.capture.setup import get_certificate_thumbprint
    cert_path, expected = _write_pem_cert(tmp_path)
    assert get_certificate_thumbprint(cert_path) == expected


def test_thumbprint_returns_none_for_missing_file(tmp_path):
    from api.capture.setup import get_certificate_thumbprint
    assert get_certificate_thumbprint(tmp_path / "nope.cer") is None


def test_thumbprint_returns_none_for_garbage_file(tmp_path):
    from api.capture.setup import get_certificate_thumbprint
    p = tmp_path / "garbage.cer"
    p.write_bytes(b"not a certificate at all")
    assert get_certificate_thumbprint(p) is None


def test_is_trusted_false_when_thumbprint_unknown(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    # Garbage file → thumbprint is None → must short-circuit to False without subprocess
    p = tmp_path / "garbage.cer"
    p.write_bytes(b"x")
    called = {"n": 0}
    def fake_run(*a, **kw):
        called["n"] += 1
        return subprocess.CompletedProcess(args=[], returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert is_certificate_trusted(p) is False
    assert called["n"] == 0


def test_is_trusted_true_on_zero_exit(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    )
    assert is_certificate_trusted(cert_path) is True


def test_is_trusted_false_on_nonzero_exit(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not found")
    )
    assert is_certificate_trusted(cert_path) is False


def test_is_trusted_false_when_certutil_missing(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    def boom(*a, **kw):
        raise FileNotFoundError("certutil")
    monkeypatch.setattr(subprocess, "run", boom)
    assert is_certificate_trusted(cert_path) is False


def test_is_trusted_false_on_timeout(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="certutil", timeout=5)
    monkeypatch.setattr(subprocess, "run", boom)
    assert is_certificate_trusted(cert_path) is False


def test_install_certificate_succeeds_on_zero_exit(tmp_path, monkeypatch):
    from api.capture.setup import install_certificate
    cert_path, _ = _write_pem_cert(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    )
    install_certificate(cert_path)  # must not raise


def test_install_certificate_raises_on_nonzero_exit(tmp_path, monkeypatch):
    from api.capture.setup import install_certificate, CertificateInstallError
    cert_path, _ = _write_pem_cert(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="access denied")
    )
    with pytest.raises(CertificateInstallError) as exc:
        install_certificate(cert_path)
    assert "access denied" in str(exc.value)


def test_install_certificate_raises_when_file_missing(tmp_path):
    from api.capture.setup import install_certificate, CertificateInstallError
    with pytest.raises(CertificateInstallError) as exc:
        install_certificate(tmp_path / "nope.cer")
    assert "not found" in str(exc.value).lower()


def test_install_certificate_raises_when_certutil_missing(tmp_path, monkeypatch):
    from api.capture.setup import install_certificate, CertificateInstallError
    cert_path, _ = _write_pem_cert(tmp_path)
    def boom(*a, **kw):
        raise FileNotFoundError("certutil")
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(CertificateInstallError) as exc:
        install_certificate(cert_path)
    assert "certutil" in str(exc.value).lower()


def test_install_certificate_endpoint_success():
    cert = _cert_stub(True)
    with patch("api.routes.setup.certificate_path", return_value=cert), \
         patch("api.routes.setup.install_certificate") as install:
        r = client.post("/api/setup/install-certificate")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    install.assert_called_once_with(cert)


def test_install_certificate_endpoint_returns_error_on_failure():
    from api.capture.setup import CertificateInstallError
    with patch("api.routes.setup.certificate_path", return_value=_cert_stub(True)), \
         patch("api.routes.setup.install_certificate", side_effect=CertificateInstallError("antivirus blocked")):
        r = client.post("/api/setup/install-certificate")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "antivirus blocked" in body["error"]


def test_install_certificate_endpoint_works_without_admin():
    # The per-user store needs no elevation, so the route must not consult admin status at all.
    cert = _cert_stub(True)
    with patch("api.routes.setup.certificate_path", return_value=cert), \
         patch("api.routes.setup.install_certificate") as install:
        r = client.post("/api/setup/install-certificate")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    install.assert_called_once_with(cert)


def test_install_certificate_endpoint_404_when_no_cert_file():
    with patch("api.routes.setup.certificate_path", return_value=_cert_stub(False)):
        r = client.post("/api/setup/install-certificate")
    assert r.status_code == 404


def test_check_prerequisites_includes_certificate_trusted(tmp_path, monkeypatch):
    from api.capture import setup as setup_module
    cert_path, _ = _write_pem_cert(tmp_path)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # mitmproxy expects ~/.mitmproxy/mitmproxy-ca-cert.cer
    mitmproxy_dir = tmp_path / ".mitmproxy"
    mitmproxy_dir.mkdir()
    (mitmproxy_dir / "mitmproxy-ca-cert.cer").write_bytes(cert_path.read_bytes())

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    )

    status = setup_module.check_prerequisites()
    assert status.has_certificate is True
    assert status.certificate_trusted is True


def test_setup_status_response_includes_certificate_trusted():
    mock_status = MagicMock(
        is_admin=True,
        has_mitmproxy=True,
        mitmproxy_version="10.1.1",
        has_certificate=True,
        certificate_path=Path("/fake/cert.cer"),
        certificate_trusted=True,
    )
    with patch("api.routes.setup.check_prerequisites", return_value=mock_status):
        r = client.get("/api/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body["certificate"] is True
    assert body["certificate_trusted"] is True


def test_check_prerequisites_certificate_trusted_false_when_no_file(tmp_path, monkeypatch):
    from api.capture import setup as setup_module
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # No cert file at all → must NOT shell out, must return False
    called = {"n": 0}
    def fake_run(*a, **kw):
        called["n"] += 1
        return subprocess.CompletedProcess(args=[], returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    status = setup_module.check_prerequisites()
    assert status.has_certificate is False
    assert status.certificate_trusted is False
    assert called["n"] == 0


# Per-user certificate store: install into CurrentUser\Root instead of LocalMachine\Root
# so the CA only affects this account. Trust checks still accept the old machine store.


def test_install_certificate_targets_the_current_user_store(tmp_path, monkeypatch):
    from api.capture.setup import install_certificate
    cert_path, _ = _write_pem_cert(tmp_path)
    calls = _record_runs(monkeypatch, [0])
    install_certificate(cert_path)
    assert calls[0][:4] == ["certutil", "-user", "-addstore", "-f"]
    assert "Root" in calls[0]


def test_is_trusted_true_when_only_in_user_store(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    calls = _record_runs(monkeypatch, [0])
    assert is_certificate_trusted(cert_path) is True
    assert "-user" in calls[0]
    assert len(calls) == 1  # found in the user store, no need to check the machine store


def test_is_trusted_falls_back_to_machine_store(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    calls = _record_runs(monkeypatch, [1, 0])  # miss in user store, hit in machine store
    assert is_certificate_trusted(cert_path) is True
    assert len(calls) == 2
    assert "-user" not in calls[1]


def test_is_trusted_false_when_in_neither_store(tmp_path, monkeypatch):
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    _record_runs(monkeypatch, [1, 1])
    assert is_certificate_trusted(cert_path) is False


def test_remove_certificate_clears_both_stores(tmp_path, monkeypatch):
    from api.capture.setup import remove_certificate
    cert_path, thumb = _write_pem_cert(tmp_path)
    calls = _record_runs(monkeypatch, [0, 0])
    removed = remove_certificate(cert_path)
    assert removed == ["user", "machine"]
    assert calls[0] == ["certutil", "-user", "-delstore", "Root", thumb]
    assert calls[1] == ["certutil", "-delstore", "Root", thumb]


def test_remove_certificate_reports_only_stores_it_cleared(tmp_path, monkeypatch):
    from api.capture.setup import remove_certificate
    cert_path, _ = _write_pem_cert(tmp_path)
    _record_runs(monkeypatch, [0, 1])  # present in user store only
    assert remove_certificate(cert_path) == ["user"]


def test_remove_certificate_falls_back_to_name_when_file_is_gone(tmp_path, monkeypatch):
    from api.capture.setup import remove_certificate
    calls = _record_runs(monkeypatch, [0, 0])
    remove_certificate(tmp_path / "gone.cer")
    assert calls[0][-1] == "mitmproxy"  # no thumbprint available, match by subject name


def test_remove_certificate_endpoint():
    cert = _cert_stub(True)
    with patch("api.routes.setup.certificate_path", return_value=cert), \
         patch("api.routes.setup.remove_certificate", return_value=["user"]) as rm:
        r = client.post("/api/setup/remove-certificate")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "removed_from": ["user"]}
    rm.assert_called_once_with(cert)


def test_install_certificate_keeps_its_window_so_the_prompt_is_visible(tmp_path, monkeypatch):
    # Adding a root CA to the per-user store makes Windows show a "Security Warning" dialog.
    # Passing CREATE_NO_WINDOW hides it and certutil then blocks forever on a prompt nobody sees.
    from api.capture.setup import install_certificate
    cert_path, _ = _write_pem_cert(tmp_path)
    seen = {}

    def fake_run(cmd, *a, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    install_certificate(cert_path)
    assert seen["creationflags"] == 0


def test_trust_check_still_hides_its_window(tmp_path, monkeypatch):
    # verifystore is read-only and never prompts, so it should stay silent.
    from api.capture.setup import is_certificate_trusted
    cert_path, _ = _write_pem_cert(tmp_path)
    seen = {}

    def fake_run(cmd, *a, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    is_certificate_trusted(cert_path)
    assert seen["creationflags"] != 0


def test_install_certificate_explains_an_unanswered_prompt(tmp_path, monkeypatch):
    from api.capture.setup import install_certificate, CertificateInstallError
    cert_path, _ = _write_pem_cert(tmp_path)

    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="certutil", timeout=120)

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(CertificateInstallError) as exc:
        install_certificate(cert_path)
    assert "prompt" in str(exc.value).lower()
