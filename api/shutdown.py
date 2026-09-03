"""
Clean up when the Tauri window goes away.

Tauri used to kill this process outright with a Job Object, so a capture's hosts redirect and its
certificate trust were never undone. The game could not connect until the app was launched again,
and the CA stayed trusted the whole time. Tauri now leaves us alone and we watch it instead.
"""

import ctypes
import os
import sys
import threading

PARENT_PID_ENV = "HUB_CZN_PARENT_PID"

# If cleanup wedges, give up and exit anyway rather than leaving an elevated process behind.
CLEANUP_DEADLINE_SECONDS = 10

_SYNCHRONIZE = 0x00100000
_INFINITE = 0xFFFFFFFF


def cleanup():
    """Undo whatever a running capture put in place. Every step is idempotent and never raises."""
    try:
        from api.capture.manager import remove_capture_entries
        remove_capture_entries()
    except Exception:
        pass
    try:
        from api.capture.setup import certificate_path, remove_capture_certificate
        remove_capture_certificate(certificate_path())
    except Exception:
        pass


def _watch(handle: int):
    """Wait for the parent to exit, clean up, then exit ourselves."""
    ctypes.windll.kernel32.WaitForSingleObject(handle, _INFINITE)
    # Armed before cleanup, so a hung certutil cannot keep this process alive forever.
    deadline = threading.Timer(CLEANUP_DEADLINE_SECONDS, lambda: os._exit(1))
    deadline.daemon = True
    deadline.start()
    cleanup()
    os._exit(0)


def watch_parent() -> bool:
    """
    Start watching the Tauri process, so we can tidy up when it goes.

    The handle is opened here rather than in the thread. If it cannot be opened we simply do not
    watch, which is safer than a thread that mistakes a bad handle for a dead parent and exits.

    Returns:
        True if a watcher was started. False when running standalone, where there is no parent.
    """
    raw = os.environ.get(PARENT_PID_ENV, "").strip()
    if sys.platform != "win32" or not raw.isdigit():
        return False

    handle = ctypes.windll.kernel32.OpenProcess(_SYNCHRONIZE, False, int(raw))
    if not handle:
        return False

    threading.Thread(target=_watch, args=(handle,), daemon=True).start()
    return True
