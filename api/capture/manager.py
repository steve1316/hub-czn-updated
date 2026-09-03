"""
Capture orchestration manager for CZN game data interception.
Handles proxy lifecycle, hosts file modification, and data capture coordination.
"""

import subprocess
import threading
import socket
import re
import ctypes
import sys
import os
from pathlib import Path
from typing import Optional, Callable

from .addon import Addon
from .setup import certificate_days_left, certificate_path, install_certificate_for_capture, remove_capture_certificate, setup_certificate
from .constants import PROXY_PORT, GAME_PORT, HOSTS_PATH

# Markers wrapping the lines we add to the hosts file, so we can find and remove them again.
HOSTS_BLOCK_START = "# CZN-CAPTURE-START"
HOSTS_BLOCK_END = "# CZN-CAPTURE-END"
_HOSTS_BLOCK_RE = r"\n*" + HOSTS_BLOCK_START + r".*?" + HOSTS_BLOCK_END + r"\n*"

# start_capture runs on its own thread while stop_capture comes in on the request thread, so hosts
# edits need to be serialised.
_hosts_lock = threading.Lock()


class CaptureError(Exception):
    """Raised when capture operations fail."""
    pass


def _flush_dns():
    """Drop the DNS cache so the hosts change takes effect. Windows only, never raises."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
    except OSError:
        pass


def has_capture_entries() -> bool:
    """
    Check whether our block is sitting in the hosts file.

    Read-only, and polled by the Setup page, so it must never write. A leftover block means the game
    is pointed at 127.0.0.1 and cannot connect.

    Returns:
        True if the block is present.
    """
    try:
        with open(HOSTS_PATH, "r") as f:
            return HOSTS_BLOCK_START in f.read()
    except OSError:
        return False


def remove_capture_entries() -> bool:
    """
    Strip our block from the hosts file. Safe to call when there is nothing to remove, and used both
    by stop_capture and at startup to clean up after a crash.

    Returns:
        True if the file was actually changed.
    """
    with _hosts_lock:
        try:
            with open(HOSTS_PATH, "r") as f:
                content = f.read()
        except OSError:
            return False
        cleaned = re.sub(_HOSTS_BLOCK_RE, "", content, flags=re.DOTALL)
        if cleaned == content:
            return False
        # The regex eats the newlines on both sides of our block, so put a single one back.
        cleaned = cleaned.rstrip("\n") + "\n" if cleaned.strip() else ""
        try:
            with open(HOSTS_PATH, "w") as f:
                f.write(cleaned)
        except OSError:
            return False
    _flush_dns()
    return True


def _is_process_elevated() -> Optional[bool]:
    """Return True if the current process has an elevated UAC token, False if not,
    None if we can't determine (e.g. non-Windows). Uses TokenElevation, which is
    accurate (IsUserAnAdmin alone returns True for any Administrators-group member
    even when the process isn't elevated)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes.wintypes as wintypes
        hToken = wintypes.HANDLE()
        TOKEN_QUERY = 0x0008
        TokenElevation = 20
        if not ctypes.windll.advapi32.OpenProcessToken(
            ctypes.windll.kernel32.GetCurrentProcess(),
            TOKEN_QUERY,
            ctypes.byref(hToken),
        ):
            return None
        try:
            elevated = wintypes.DWORD(0)
            size = wintypes.DWORD(0)
            if ctypes.windll.advapi32.GetTokenInformation(
                hToken, TokenElevation,
                ctypes.byref(elevated),
                ctypes.sizeof(elevated),
                ctypes.byref(size),
            ):
                return bool(elevated.value)
        finally:
            ctypes.windll.kernel32.CloseHandle(hToken)
    except Exception:
        pass
    return None


def _is_controlled_folder_access_enabled() -> Optional[bool]:
    """Detect if Microsoft Defender Controlled Folder Access is enabled.
    Returns True/False if PowerShell + Defender are available, None otherwise.
    CFA blocks writes to %WinDir%\\System32\\drivers\\etc\\hosts even from elevated
    processes, returning a generic EACCES with no specific indicator."""
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-MpPreference).EnableControlledFolderAccess"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            # Get-MpPreference returns 0 (Disabled), 1 (Enabled), or 2 (AuditMode)
            value = result.stdout.strip()
            return value in ("1", "2")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _is_readonly(path: Path) -> bool:
    """Check whether a Windows file has the read-only attribute set."""
    try:
        return not (os.stat(path).st_mode & 0o200)
    except OSError:
        return False


def _diagnose_hosts_write_failure(path: Path, original_error: Exception) -> str:
    """Build an actionable error message based on which Windows mechanism is
    most likely blocking the write. Order matters: report the most fixable
    cause that's confirmed present."""
    parts = [f"Cannot write to hosts file at {path}."]

    elevated = _is_process_elevated()
    if elevated is False:
        parts.append(
            "The app is running as Administrator according to the Windows "
            "group check, but the process token is NOT elevated. Restart "
            "Hub CZN by right-clicking the app icon → 'Run as administrator', "
            "and accept the UAC prompt."
        )
        parts.append(f"Original error: {original_error}")
        return "\n\n".join(parts)

    if _is_readonly(path):
        parts.append(
            "The hosts file has the read-only attribute. Clear it from an "
            "admin PowerShell with:\n"
            "  Set-ItemProperty -Path \"$env:WINDIR\\System32\\drivers\\etc\\hosts\" -Name IsReadOnly -Value $false"
        )
        parts.append(f"Original error: {original_error}")
        return "\n\n".join(parts)

    cfa = _is_controlled_folder_access_enabled()
    if cfa is True:
        parts.append(
            "Microsoft Defender Controlled Folder Access (CFA) is enabled and "
            "is most likely blocking the write — CFA blocks ALL writes to "
            "%WinDir%\\System32\\drivers\\etc\\ even from admin processes.\n\n"
            "Two options:\n"
            "  1) Allow Hub CZN through CFA (recommended):\n"
            "     Windows Security → Virus & threat protection → "
            "     Manage ransomware protection → Allow an app through "
            "     Controlled folder access → Add the Hub CZN executable.\n"
            "  2) Temporarily disable CFA while capturing:\n"
            "     Windows Security → same path → toggle Controlled folder access off."
        )
        parts.append(f"Original error: {original_error}")
        return "\n\n".join(parts)

    # Generic — couldn't pinpoint a specific cause.
    parts.append(
        "Could not pinpoint the specific cause. Likely candidates:\n"
        "  - Microsoft Defender Controlled Folder Access (could not query)\n"
        "  - Third-party antivirus / endpoint security software blocking hosts edits\n"
        "  - Explicit Deny ACL on the hosts file (corporate / hardened machines)\n"
        "  - Another process holding an exclusive lock on the file\n\n"
        "Try: temporarily pausing antivirus, or running 'icacls "
        f"\"{path}\"' from an elevated prompt to check permissions."
    )
    parts.append(f"Original error: {original_error}")
    return "\n\n".join(parts)


class CaptureManager:
    """
    Manages the complete capture workflow:
    - Proxy server lifecycle
    - Hosts file modification/restoration
    - Game server resolution
    - Data capture coordination
    """

    def __init__(
        self,
        output_folder: Path,
        log_callback: Callable[[str, Optional[str]], None],
        status_callback: Optional[Callable[[str], None]] = None,
        live_update_callback: Optional[Callable[[], None]] = None
    ):
        """
        Initialize the capture manager.

        Args:
            output_folder: Directory to save captured JSON files
            log_callback: Function(message, tag) for logging (tag can be None, "success", "error", "warning", "info")
            status_callback: Optional function(status) for status updates
            live_update_callback: Optional function() called when data changes (for auto-reload)
        """
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self.log_callback = log_callback
        self.status_callback = status_callback
        self.live_update_callback = live_update_callback

        self.capturing = False
        self.game_server_ips = {}
        self.original_hosts_content = None
        self.current_region = "global"  # Default region

        # mitmproxy runs in-process on its own thread rather than as a mitmdump subprocess.
        self.addon = None
        self._master = None
        self._proxy_thread = None
        self._proxy_ready = threading.Event()

    def is_capturing(self) -> bool:
        """Check if currently capturing."""
        return self.capturing

    def get_latest_capture(self) -> Optional[Path]:
        """
        Get path to most recent capture file.

        Returns:
            Path to latest capture file, or None if no snapshots exist
        """
        files = list(self.output_folder.glob("memory_fragments_*.json"))
        return max(files, key=lambda f: f.stat().st_mtime) if files else None

    def get_latest_rescue_records(self) -> Optional[Path]:
        """
        Get path to most recent rescue records file.

        Returns:
            Path to latest rescue records file, or None if none exist
        """
        files = list(self.output_folder.glob("rescue_records_*.json"))
        return max(files, key=lambda f: f.stat().st_mtime) if files else None

    def _read_detected_region(self, capture_file: Path) -> Optional[str]:
        """Read detected_region from capture file."""
        import json
        try:
            with open(capture_file, 'r') as f:
                data = json.load(f)
            return data.get("detected_region")
        except Exception:
            return None

    def open_snapshots_folder(self):
        """Open snapshots folder in file explorer."""
        self.output_folder.mkdir(exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.output_folder)
        else:
            subprocess.run(["xdg-open", str(self.output_folder)])

    def set_region(self, region_id: str):
        """Set the active server region for capture."""
        from .constants import SERVERS
        if region_id not in SERVERS:
            raise ValueError(f"Unknown region: {region_id}")
        self.current_region = region_id

    def resolve_game_server(self):
        """
        Resolve game server hostnames to IP addresses for current region.
        Stores results in self.game_server_ips.
        """
        from .constants import SERVERS
        server_config = SERVERS[self.current_region]
        self.game_server_ips = {}
        for host in server_config.hosts:
            try:
                ip = socket.gethostbyname(host)
                self.game_server_ips[host] = ip
            except socket.gaierror:
                pass

    def modify_hosts_file(self) -> str:
        """
        Modify Windows hosts file to redirect game traffic to local proxy.

        Returns:
            Original hosts file content (for restoration)

        Raises:
            CaptureError: With actionable diagnostic message on failure.
        """
        with _hosts_lock:
            try:
                with open(HOSTS_PATH, "r") as f:
                    content = f.read()
            except Exception as e:
                raise CaptureError(
                    f"Cannot read hosts file at {HOSTS_PATH}: {e}\n"
                    f"This is unusual - the file should be world-readable."
                )

            # Don't modify if already modified
            if HOSTS_BLOCK_START in content:
                return content

            # Check write access before building the new content so we fail with a specific reason.
            # Opening for append needs the same rights as a real edit but changes nothing.
            try:
                with open(HOSTS_PATH, "a"):
                    pass
            except (PermissionError, OSError) as e:
                raise CaptureError(_diagnose_hosts_write_failure(HOSTS_PATH, e))

            # Build entries and write the real change.
            from .constants import SERVERS
            server_config = SERVERS[self.current_region]
            entries = ["\n" + HOSTS_BLOCK_START]
            for host in server_config.hosts:
                entries.append(f"127.0.0.1 {host}")
            entries.append(HOSTS_BLOCK_END + "\n")
            new_content = content + "\n".join(entries)

            try:
                with open(HOSTS_PATH, "w") as f:
                    f.write(new_content)
            except (PermissionError, OSError) as e:
                # Probe succeeded but real write failed - race condition or transient lock.
                raise CaptureError(
                    f"Hosts file write failed after access probe succeeded: {e}\n"
                    f"Possible cause: another process locked the file between checks. "
                    f"Common culprits: antivirus real-time scan, DNS resolver service. "
                    f"Retry, and if it persists, temporarily pause the suspected service."
                )

        _flush_dns()
        return content

    def restore_hosts_file(self):
        """Put the hosts file back the way it was by removing the entries modify_hosts_file() added."""
        try:
            remove_capture_entries()
        except Exception as e:
            self.log_callback(f"Failed to restore hosts: {e}", "error")

    def _find_dictionary_path(self) -> Optional[Path]:
        """
        Find the zstd dictionary file.
        Searches in order: output_folder, Vribbels folder, bundled location.
        If found in bundled location, copies to output_folder for addon script access.

        Returns:
            Path to dictionary file if found, None otherwise
        """
        import shutil
        dict_name = "zstd_dictionary.bin"

        # Check output folder first (always accessible by addon script)
        dict_path = self.output_folder / dict_name
        if dict_path.exists():
            return dict_path

        # Check Vribbels folder (development mode)
        vribbels_folder = Path(__file__).parent.parent
        source_path = vribbels_folder / dict_name
        if source_path.exists():
            return source_path

        # Check if running from PyInstaller bundle
        if hasattr(sys, '_MEIPASS'):
            bundled_path = Path(sys._MEIPASS) / dict_name
            if bundled_path.exists():
                # Copy to output folder so addon script can access it
                # (addon runs as separate process without _MEIPASS access)
                try:
                    dest_path = self.output_folder / dict_name
                    shutil.copy2(bundled_path, dest_path)
                    return dest_path
                except Exception:
                    # Return bundled path as fallback
                    return bundled_path

        return None

    def _on_saved(self, kind: str):
        """
        The addon wrote a snapshot, so tell the UI to reload.

        Args:
            kind: "fragments", "rescue" or "battle". Only a fragments save changes the headline
                status, which is what the old stdout parser did too.
        """
        if kind == "fragments" and self.status_callback:
            self.status_callback("[OK] Data Captured!")
        if self.live_update_callback:
            self.live_update_callback()

    def _run_proxy(self, real_ip: str):
        """
        Run mitmproxy on this thread's own event loop until stop_capture asks it to exit.

        Args:
            real_ip: Game server IP to forward to. Using the IP avoids resolving the hostname again
                through the hosts file we just redirected.
        """
        import asyncio
        from mitmproxy import options
        from mitmproxy.tools.dump import DumpMaster

        async def run():
            opts = options.Options(
                listen_host="127.0.0.1",
                listen_port=PROXY_PORT,
                mode=[f"reverse:https://{real_ip}:{GAME_PORT}/"],
                ssl_insecure=True,
            )
            # upstream_cert and friends belong to the proxy addons that DumpMaster loads, so they
            # can only be set once it exists.
            master = DumpMaster(opts, with_termlog=False, with_dumper=False)
            master.options.update(upstream_cert=False, keep_host_header=True, connection_strategy="lazy")
            master.addons.add(self.addon)
            self._master = master
            self._proxy_ready.set()
            await master.run()

        try:
            asyncio.run(run())
        except Exception as e:
            self.log_callback(f"[proxy] {e}", "error")
        finally:
            self._master = None
            self._proxy_ready.set()

    def _trust_certificate(self):
        """
        Generate the CA if it is missing and add it to the machine store for this capture.

        Raises:
            CaptureError: If the certificate cannot be generated or trusted, since capture would
                only fail later with a confusing TLS error.
        """
        try:
            cert = certificate_path()
            days_left = certificate_days_left(cert) if cert.exists() else None
            if not cert.exists():
                setup_certificate()
            elif days_left is not None and days_left < 0:
                # Re-adding an expired CA just re-trusts something the game will reject, so make a
                # new one instead. mitmproxy writes a fresh CA when the old files are gone.
                self.log_callback("Certificate has expired, generating a new one", "warning")
                for stale in cert.parent.glob("mitmproxy-ca*"):
                    stale.unlink(missing_ok=True)
                setup_certificate()
            install_certificate_for_capture(cert)
        except Exception as exc:
            raise CaptureError(f"Could not trust the capture certificate: {exc}")
        self.log_callback("Certificate trusted for this capture", "success")

    def _untrust_certificate(self):
        """Drop the CA from the machine store. Never raises - stopping must not fail on cleanup."""
        try:
            if remove_capture_certificate(certificate_path()):
                self.log_callback("Certificate trust removed", "success")
        except Exception:
            pass

    def start_capture(self, debug_mode: bool = False):
        """
        Start capturing: check we are admin, point the game host at us in the hosts file, then run
        mitmproxy in-process with our addon attached.

        Args:
            debug_mode: If True, log every WebSocket message to a debug file

        Raises:
            CaptureError: If capture cannot be started
        """
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                raise CaptureError(
                    "Administrator privileges required. Please restart as Administrator."
                )
        except AttributeError:
            pass  # not on Windows

        self.log_callback("Starting capture...", None)

        # Importing mitmproxy takes the better part of a second. Get it out of the way before the
        # hosts redirect goes in, otherwise the game points at a proxy that is not listening yet.
        import mitmproxy.tools.dump  # noqa: F401

        self.resolve_game_server()
        if not self.game_server_ips:
            raise CaptureError("Could not resolve game servers.")
        real_ip = list(self.game_server_ips.values())[0]

        # Trust the CA only while we are actually capturing. Goes in before the redirect so the
        # game never meets the proxy with an untrusted leaf.
        self._trust_certificate()

        self.modify_hosts_file()
        self.log_callback("Hosts file modified", "success")

        dict_path = self._find_dictionary_path()
        if not dict_path:
            self.log_callback("Warning: zstd dictionary not found", "warning")

        self.addon = Addon(
            self.output_folder,
            dict_path=dict_path,
            log_callback=lambda msg: self.log_callback(msg, None),
            debug_mode=debug_mode,
            on_saved=self._on_saved,
        )

        self._proxy_ready.clear()
        self._proxy_thread = threading.Thread(target=self._run_proxy, args=(real_ip,), daemon=True)
        self._proxy_thread.start()

        # _run_proxy also signals ready from its finally block, so a set event only means
        # "started or died". Checking _master is what tells the two apart.
        if not self._proxy_ready.wait(timeout=15) or self._master is None:
            self.restore_hosts_file()
            raise CaptureError(
                f"Proxy failed to start on port {PROXY_PORT}. Something else may be using it. "
                "Check the capture log for details."
            )

        self.capturing = True
        if self.status_callback:
            self.status_callback("Capturing...")
        self.log_callback("Capture started! Launch the game and load into the main menu.", "success")

    def wait(self):
        """Block until the proxy stops. The capture route uses this to keep its worker thread alive."""
        if self._proxy_thread:
            self._proxy_thread.join()

    def stop_capture(self) -> Optional[tuple[Path, Optional[str]]]:
        """
        Stop the proxy, put the hosts file back, and report the newest capture file.

        Returns:
            (path, detected_region) for the newest capture, or None if nothing was captured.
        """
        if not self.capturing:
            return None

        if self._master:
            self._master.shutdown()  # documented as thread-safe
        if self._proxy_thread:
            self._proxy_thread.join(timeout=10)
        self._proxy_thread = None
        # The addon's callbacks close over this manager, so drop it or the pair leaks until the
        # cycle collector runs, holding the debug file handle and the captured data open.
        self.addon = None

        self.restore_hosts_file()
        self._untrust_certificate()
        self.capturing = False

        if self.status_callback:
            self.status_callback("[O] Stopped")

        latest = self.get_latest_capture()
        if latest:
            detected = self._read_detected_region(latest)
            self.log_callback(f"Capture stopped. File: {latest.name}", "success")
            return (latest, detected)

        self.log_callback("Capture stopped. No data captured.", None)
        return None
