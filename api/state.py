from __future__ import annotations

import queue
import time

from api.frozen_path import add_vribbels_to_path
add_vribbels_to_path()

from optimizer import GearOptimizer


def clear_stale_hosts_entries():
    """
    Drop any capture entries left in the hosts file by a previous run.

    The Tauri Job Object kills the sidecar outright, so nothing gets a chance to clean up if the app
    crashes or is closed mid-capture. Without this the game stays pointed at 127.0.0.1 and cannot
    connect, with no way to fix it from inside the app.
    """
    try:
        # Import via the api package, not the bare "capture" alias. Both work because of the path
        # hack in frozen_path, but they load as separate modules with separate module-level state.
        from api.capture.manager import remove_capture_entries
        if remove_capture_entries():
            print("Removed leftover hosts entries from a previous capture", flush=True)
    except Exception:
        pass


def clear_stale_certificate_trust():
    """
    Drop any machine-store CA left behind by a previous run.

    Capture trusts the CA only while it runs, but the Tauri Job Object kills the sidecar outright,
    so a crash mid-capture would otherwise leave the machine permanently trusting it. Only the
    machine store is touched - a per-user copy is the user's own choice.
    """
    try:
        from api.capture.setup import certificate_path, remove_capture_certificate
        if remove_capture_certificate(certificate_path()):
            print("Removed leftover certificate trust from a previous capture", flush=True)
    except Exception:
        pass


class AppState:
    def __init__(self):
        self.optimizer = GearOptimizer()
        self.data_loaded: bool = False
        self.loaded_file: str | None = None

        # Capture state
        self.capture_running: bool = False
        self.capture_region: str = "global"
        self.rescue_file_path: str | None = None
        self.log_queue: queue.SimpleQueue = queue.SimpleQueue()

        # Optimizer job state
        self.job_id: str | None = None
        self.cancel_flag: list[bool] = [False]

        # Auto-scroll state
        self.autoscroll_running: bool = False

        # CaptureManager is created lazily on first start
        self._capture_manager = None

        clear_stale_hosts_entries()
        clear_stale_certificate_trust()
        self._auto_load_latest()

    def _auto_load_latest(self):
        """On startup, load the most recent snapshot so Fragments/Combatants are available immediately."""
        try:
            from api.capture.constants import OUTPUT_DIR
            frags = sorted(OUTPUT_DIR.glob("memory_fragments_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not frags:
                return
            latest = frags[0]
            self.optimizer.load_data(str(latest))
            self.data_loaded = True
            self.loaded_file = str(latest)
            # Also set rescue_file_path to the latest rescue snapshot if one exists
            rescue = sorted(OUTPUT_DIR.glob("rescue_records_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            self.rescue_file_path = str(rescue[0]) if rescue else None
        except Exception:
            pass

    def get_capture_manager(self):
        """Return existing manager or create a new one for this session."""
        if self._capture_manager is None:
            from api.capture.manager import CaptureManager
            from api.capture.constants import OUTPUT_DIR

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            def _log(msg: str, tag: str | None = None):
                if tag in ("error", "success", "warning", "info"):
                    level = tag
                else:
                    level = "info"
                    msg_lower = msg.lower()
                    if msg_lower.startswith("error") or "failed" in msg_lower:
                        level = "error"
                    elif "saved:" in msg_lower or msg_lower.startswith("[live]"):
                        level = "success"
                    elif "warning" in msg_lower:
                        level = "warning"
                self.log_queue.put({
                    "level": level,
                    "message": msg,
                    "timestamp": time.strftime("%H:%M:%S"),
                })

            def _on_data_saved():
                mgr = self._capture_manager
                if mgr is None:
                    return
                latest = mgr.get_latest_capture()
                if latest:
                    try:
                        self.optimizer.load_data(str(latest))
                        self.data_loaded = True
                        self.loaded_file = str(latest)
                        self.rescue_file_path = str(latest)
                    except Exception:
                        pass

            self._capture_manager = CaptureManager(
                output_folder=OUTPUT_DIR,
                log_callback=_log,
                live_update_callback=_on_data_saved,
            )

        return self._capture_manager

    def reset_capture_manager(self):
        """Discard manager after stop so next start is fresh."""
        self._capture_manager = None


state = AppState()
