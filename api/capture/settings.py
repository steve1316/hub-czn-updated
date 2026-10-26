"""
Capture settings kept next to the snapshots, so they survive restarts.

The sidecar has to read these at start-up before any UI exists, which is why they live on disk here and not in the browser.
"""

import json
import logging

from api.capture.constants import OUTPUT_DIR

SETTINGS_PATH = OUTPUT_DIR / "capture_settings.json"

DEFAULTS = {"auto_start": False, "region": "global"}

REGIONS = ("global", "asia")


def load_capture_settings() -> dict:
    """
    Read the saved settings, falling back to the defaults for anything missing or invalid.

    Returns:
        A dict with `auto_start` (bool) and `region` ("global" or "asia").
    """
    settings = dict(DEFAULTS)
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            if isinstance(raw.get("auto_start"), bool):
                settings["auto_start"] = raw["auto_start"]
            if raw.get("region") in REGIONS:
                settings["region"] = raw["region"]
    except (OSError, ValueError):
        pass
    return settings


def save_capture_settings(settings: dict) -> dict:
    """
    Write the settings to disk. A failed write is logged and not raised.

    Args:
        settings: The full settings dict to store.

    Returns:
        The settings as stored (unknown keys dropped).
    """
    clean = {"auto_start": bool(settings.get("auto_start", False)), "region": settings.get("region") if settings.get("region") in REGIONS else "global"}
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    except OSError as exc:
        logging.getLogger(__name__).warning("Failed to save capture settings: %s", exc)
    return clean
