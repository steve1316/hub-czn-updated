# api/routes/setup.py
from __future__ import annotations

from api.frozen_path import add_vribbels_to_path
add_vribbels_to_path()

from pathlib import Path

from fastapi import APIRouter, HTTPException
from api.capture.setup import (
    certificate_path,
    check_prerequisites,
    setup_certificate,
    open_certificate,
    install_certificate,
    remove_certificate,
    CertificateInstallError,
)

router = APIRouter()


@router.get("/setup/status")
def get_setup_status():
    s = check_prerequisites()
    return {
        "admin": s.is_admin,
        "mitmproxy": s.has_mitmproxy,
        "mitmproxy_version": s.mitmproxy_version,
        "certificate": s.has_certificate,
        "certificate_trusted": s.certificate_trusted,
        "can_write_hosts": s.can_write_hosts,
        "hosts_block_reason": s.hosts_block_reason,
    }


@router.post("/setup/generate-cert")
def post_generate_cert():
    try:
        setup_certificate()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _existing_cert() -> Path:
    """Return the CA path, or 404 if it has not been generated yet."""
    cert = certificate_path()
    if not cert.exists():
        raise HTTPException(status_code=404, detail="Certificate not found. Generate it first.")
    return cert


@router.post("/setup/open-cert")
def post_open_cert():
    try:
        open_certificate(_existing_cert())
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/setup/install-certificate")
def post_install_certificate():
    # No admin check: the cert goes into the per-user store, which any account can write.
    try:
        install_certificate(_existing_cert())
        return {"ok": True}
    except CertificateInstallError as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/setup/remove-certificate")
def post_remove_certificate():
    return {"ok": True, "removed_from": remove_certificate(_existing_cert())}
