"""
Setup utilities for capture prerequisites.
Handles CA certificate generation, trust, and prerequisite checking.
"""

import subprocess
import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Thumbprints already known to be absent from the machine store, so the polled status check does not
# keep shelling out for them.
_machine_store_misses = set()


class CertificateInstallError(Exception):
    """Raised when certificate installation fails."""
    pass


def certificate_path() -> Path:
    """Where mitmproxy writes its CA. Not a constant so tests can patch Path.home()."""
    return Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"


def get_certificate_thumbprint(cert_path: Path) -> Optional[str]:
    """
    Compute the SHA-1 thumbprint of a certificate file (uppercase hex).
    Handles both PEM (mitmproxy's default for .cer) and DER encodings.
    Returns None if the file is missing or cannot be parsed.
    """
    try:
        data = cert_path.read_bytes()
    except (FileNotFoundError, OSError):
        return None

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        try:
            cert = x509.load_pem_x509_certificate(data)
        except ValueError:
            cert = x509.load_der_x509_certificate(data)
        return cert.fingerprint(hashes.SHA1()).hex().upper()
    except Exception:
        return None


class CertutilPromptTimeout(Exception):
    """Raised when certutil sat waiting on the Windows security prompt for too long."""
    pass


def _run_certutil(args: list, timeout: int = 15, interactive: bool = False):
    """
    Run certutil. Never raises except for a timeout on an interactive call.

    Args:
        args: Arguments to pass after the exe name.
        timeout: Seconds to wait before giving up.
        interactive: True for calls that make Windows show its "Security Warning" consent dialog,
            which adding or deleting a root CA in the per-user store always does. Those must keep
            their window, otherwise the prompt is invisible and certutil waits forever.

    Returns:
        The CompletedProcess, or None if certutil could not be run at all.

    Raises:
        CertutilPromptTimeout: If an interactive call timed out, which means the prompt went
            unanswered rather than certutil being broken.
    """
    creationflags = 0 if interactive else getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            ["certutil", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        if interactive:
            raise CertutilPromptTimeout(
                "Windows asked for confirmation and the prompt was not answered in time. "
                "Click Yes on the Windows security prompt, then try again."
            )
        return None
    except (FileNotFoundError, OSError):
        return None


def is_certificate_trusted(cert_path: Path) -> bool:
    """
    Check whether the certificate is trusted. Looks in the per-user Root store first, then the machine store
    so certs installed by older versions still count.

    Args:
        cert_path: Path to the certificate file.

    Returns:
        True if the thumbprint is in either store. False on any failure. Never raises.
    """
    thumbprint = get_certificate_thumbprint(cert_path)
    if not thumbprint:
        return False
    for store_args in (["-user"], []):
        # Misses are remembered because the Setup page polls this every 5 seconds. Capture installs
        # and removes the machine copy as it runs, so both of those clear the memo.
        if not store_args and thumbprint in _machine_store_misses:
            continue
        result = _run_certutil([*store_args, "-verifystore", "Root", thumbprint], timeout=5)
        if result is None:
            return False
        if result.returncode == 0:
            return True
        if not store_args:
            _machine_store_misses.add(thumbprint)
    return False


def remove_certificate(cert_path: Path) -> list[str]:
    """
    Delete the CA from both Root stores. Matches on the thumbprint, or on the name "mitmproxy" when the
    cert file is already gone. Clearing the machine store needs admin, so it usually fails now that we
    install per-user.

    Args:
        cert_path: Path to the certificate file.

    Returns:
        Names of the stores it was actually removed from, e.g. ["user"].
    """
    match = get_certificate_thumbprint(cert_path) or "mitmproxy"
    _machine_store_misses.discard(match)
    removed = []
    for name, store_args in (("user", ["-user"]), ("machine", [])):
        # Root-store edits make Windows show a consent prompt, so keep the window and wait.
        result = _run_certutil([*store_args, "-delstore", "Root", match], timeout=120, interactive=True)
        if result is not None and result.returncode == 0:
            removed.append(name)
    return removed


def install_certificate_for_capture(cert_path: Path) -> None:
    """
    Add the CA to the machine Root store for the duration of a capture.

    The per-user store always makes Windows show a consent dialog, which would mean a click every
    time capture starts. The machine store is silent because the sidecar is already elevated, so
    the trade is a wider store for a much shorter window - minutes instead of forever.

    Args:
        cert_path: Path to the certificate file.

    Raises:
        CertificateInstallError: If the file is missing or certutil fails.
    """
    if not cert_path.exists():
        raise CertificateInstallError(f"Certificate file not found: {cert_path}")
    _machine_store_misses.clear()
    result = _run_certutil(["-addstore", "-f", "Root", str(cert_path)], timeout=30)
    if result is None:
        raise CertificateInstallError("certutil.exe could not be run")
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "unknown error").strip()
        raise CertificateInstallError(msg)


def remove_capture_certificate(cert_path: Path) -> bool:
    """
    Take the CA back out of the machine Root store. Safe to call when it was never there, and used
    both when capture stops and at startup to clean up after a crash.

    Deleting from the machine store while elevated does not prompt, so this stays windowless. It
    never touches the per-user store, which is the user's own choice to install or remove.

    Args:
        cert_path: Path to the certificate file.

    Returns:
        True if a certificate was actually removed.
    """
    match = get_certificate_thumbprint(cert_path) or "mitmproxy"
    _machine_store_misses.discard(match)
    result = _run_certutil(["-delstore", "Root", match], timeout=30)
    return result is not None and result.returncode == 0


def install_certificate(cert_path: Path) -> None:
    """
    Add the certificate to the current user's Root store. Per-user keeps it away from every other account
    on the PC and needs no admin rights. Idempotent.

    Args:
        cert_path: Path to the certificate file.

    Raises:
        CertificateInstallError: If the file is missing or certutil fails.
    """
    if not cert_path.exists():
        raise CertificateInstallError(f"Certificate file not found: {cert_path}")
    # Adding a root CA to the per-user store always makes Windows show a "Security Warning"
    # dialog. It must stay visible or certutil blocks forever on a prompt nobody can see.
    try:
        result = _run_certutil(["-user", "-addstore", "-f", "Root", str(cert_path)], timeout=120, interactive=True)
    except CertutilPromptTimeout as exc:
        raise CertificateInstallError(str(exc))
    if result is None:
        raise CertificateInstallError("certutil.exe could not be run")
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "unknown error").strip()
        raise CertificateInstallError(msg)


@dataclass
class PrerequisiteStatus:
    """Status of capture system prerequisites."""
    is_admin: bool
    has_mitmproxy: bool
    mitmproxy_version: Optional[str]
    has_certificate: bool
    certificate_path: Optional[Path]
    certificate_trusted: bool
    can_write_hosts: bool = True
    hosts_block_reason: Optional[str] = None


def check_prerequisites() -> PrerequisiteStatus:
    """
    Check if all prerequisites for capture system are met.

    Returns:
        PrerequisiteStatus object with current status of all requirements
    """
    # Check admin privileges (Windows only) using TokenElevation.
    is_admin = False
    try:
        import ctypes.wintypes as wintypes
        OpenProcessToken = ctypes.windll.advapi32.OpenProcessToken
        OpenProcessToken.restype = wintypes.BOOL
        OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        GetTokenInformation = ctypes.windll.advapi32.GetTokenInformation
        GetTokenInformation.restype = wintypes.BOOL
        GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

        hToken = wintypes.HANDLE()
        if OpenProcessToken(ctypes.windll.kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(hToken)):
            try:
                elevated = wintypes.DWORD(0)
                size = wintypes.DWORD(0)
                if GetTokenInformation(hToken, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)):
                    is_admin = bool(elevated.value)
            finally:
                ctypes.windll.kernel32.CloseHandle(hToken)
    except Exception:
        pass

    # mitmproxy runs in-process and ships inside the sidecar, so this is just an import check.
    # It used to spawn "mitmdump --version" on every status poll, which was slow.
    has_mitmproxy = False
    mitmproxy_version = None
    try:
        from mitmproxy import version as mitmproxy_version_module
        has_mitmproxy = True
        mitmproxy_version = mitmproxy_version_module.VERSION
    except Exception:
        pass

    # Check certificate
    cert_path = certificate_path()
    has_certificate = cert_path.exists()
    certificate_trusted = is_certificate_trusted(cert_path) if has_certificate else False

    can_write_hosts, hosts_block_reason = _probe_hosts_writable()

    return PrerequisiteStatus(
        is_admin=is_admin,
        has_mitmproxy=has_mitmproxy,
        mitmproxy_version=mitmproxy_version,
        has_certificate=has_certificate,
        certificate_path=cert_path if has_certificate else None,
        certificate_trusted=certificate_trusted,
        can_write_hosts=can_write_hosts,
        hosts_block_reason=hosts_block_reason,
    )


def _probe_hosts_writable() -> tuple[bool, Optional[str]]:
    """
    Check the hosts file is writable so the Setup tab can warn before the user clicks Start Capture.

    Opening for append needs the same rights as a real edit but writes nothing. That matters because
    the Setup page polls this every 5 seconds, and a probe that rewrote the file could clobber a
    running capture's redirect.

    Returns:
        (writable, blocking_reason). The reason is a user-readable message, or None when fine.
    """
    if sys.platform != "win32":
        return True, None
    from . import constants
    from .manager import _diagnose_hosts_write_failure
    hosts_path = constants.HOSTS_PATH
    try:
        with open(hosts_path, "r"):
            pass
    except Exception as e:
        return False, f"Cannot read hosts file: {e}"
    try:
        with open(hosts_path, "a"):
            pass
        return True, None
    except (PermissionError, OSError) as e:
        return False, _diagnose_hosts_write_failure(hosts_path, e)


def setup_certificate() -> Path:
    """
    Create the mitmproxy CA if it is not there yet. Done in-process, so mitmdump does not have to be
    installed and there is no 3 second sleep waiting for a subprocess.

    Returns:
        Path to the certificate.

    Raises:
        Exception: If the certificate could not be created.
    """
    from mitmproxy import certs

    cert_path = certificate_path()
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    certs.CertStore.from_store(cert_path.parent, "mitmproxy", key_size=2048)
    if not cert_path.exists():
        raise Exception("Certificate was not generated")
    return cert_path


def open_certificate(cert_path: Path) -> None:
    """
    Open certificate file in Windows (for manual installation).

    Args:
        cert_path: Path to certificate file

    Raises:
        Exception: If unable to open certificate
    """
    if not cert_path.exists():
        raise FileNotFoundError(f"Certificate not found: {cert_path}")

    try:
        os.startfile(str(cert_path))
    except Exception as e:
        raise Exception(f"Failed to open certificate: {e}")