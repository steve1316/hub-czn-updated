"""
Tool functions for the Hub CZN dev MCP server.

Each function takes a `HubClient` so tests can pass a stub. This module does not import the `mcp` SDK.
"""
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import requests

DEFAULT_URL = "http://127.0.0.1:7842"
DEFAULT_TOKEN = "dev"
REPO = Path(__file__).resolve().parent.parent.parent
REPLAY_SCRIPT = REPO / "scripts" / "replay_capture.py"
REPLAY_TIMEOUT = 600


class HubClient:
    """Tiny HTTP client for the sidecar. Sends the API token on every call."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        """
        Args:
            base_url: Sidecar base URL. Defaults to `HUB_CZN_API_URL` or the dev port.
            token: API token. Defaults to `HUB_CZN_API_TOKEN` or `dev`.
        """
        self.base_url = (base_url or os.environ.get("HUB_CZN_API_URL") or DEFAULT_URL).rstrip("/")
        self.token = token if token is not None else os.environ.get("HUB_CZN_API_TOKEN", DEFAULT_TOKEN)

    def request(self, method: str, path: str, **kwargs):
        """
        Call an endpoint and return its parsed JSON body.

        Args:
            method: HTTP method.
            path: Path starting with `/api/`.
            **kwargs: Passed to `requests.request` (`params`, `json`).

        Returns:
            The decoded JSON body, or `{"error": ...}` on a connection problem or HTTP error status.
        """
        try:
            resp = requests.request(method, self.base_url + path, headers={"X-Hub-Token": self.token}, timeout=30, **kwargs)
        except requests.RequestException as exc:
            return {"error": f"Cannot reach sidecar at {self.base_url}: {exc}"}
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        if resp.status_code >= 400:
            return {"error": f"HTTP {resp.status_code}", "detail": body}
        return body


def capture_status(client) -> dict:
    """Return whether capture is running, plus region, admin flag and rescue file."""
    return client.request("GET", "/api/capture/status")


def capture_start(client, region: str = "global", debug: bool = False) -> dict:
    """Start capture for `region` ("global" or "asia"). Needs an elevated sidecar."""
    return client.request("POST", "/api/capture/start", json={"region": region, "debug": debug})


def capture_stop(client) -> dict:
    """Stop capture and restore the hosts file."""
    return client.request("POST", "/api/capture/stop")


def setup_status(client) -> dict:
    """Return prerequisite checks: admin, mitmproxy, certificate, hosts redirect."""
    return client.request("GET", "/api/setup/status")


def rescue_records(client) -> list | dict:
    """Return the processed rescue records from the latest rescue snapshot."""
    return client.request("GET", "/api/rescue/records")


def capture_log_tail(client, n: int = 50) -> dict:
    """Return the last `n` capture log entries (1-500), oldest first."""
    return client.request("GET", "/api/capture/log", params={"n": n})


def latest_snapshot(client, limit: int = 20) -> dict:
    """
    Summarise the loaded snapshot and include a sample of its fragments.

    Args:
        client: Sidecar client.
        limit: How many fragments to include in `fragments`.

    Returns:
        Dict with `status`, `summary` (counts by slot, set and rarity) and `fragments`.
    """
    status = client.request("GET", "/api/status")
    if not isinstance(status, dict) or "error" in status or not status.get("data_loaded"):
        return {"status": status, "summary": None, "fragments": []}
    frags = client.request("GET", "/api/fragments")
    if not isinstance(frags, list):
        return {"status": status, "summary": None, "fragments": frags}
    summary = {
        "total": len(frags),
        "by_slot": dict(Counter(f.get("slot_name") for f in frags)),
        "by_set": dict(Counter(f.get("set_name") for f in frags)),
        "by_rarity": dict(Counter(f.get("rarity") for f in frags)),
        "equipped": sum(1 for f in frags if f.get("equipped_to") is not None),
    }
    return {"status": status, "summary": summary, "fragments": frags[: max(0, limit)]}


def replay_capture(path: str | None = None, runner=subprocess.run) -> dict:
    """
    Run `scripts/replay_capture.py` and return the report path and a short summary.

    Args:
        path: Capture `.jsonl` file. Defaults to the newest one in the snapshots folder.
        runner: Subprocess runner, replaced in tests.

    Returns:
        Dict with `ok`, `report` (path or None), `summary` (script output lines) and `stderr` on failure.
    """
    cmd = [sys.executable, str(REPLAY_SCRIPT)] + ([path] if path else [])
    try:
        proc = runner(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=REPLAY_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "report": None, "summary": [], "stderr": f"Timed out after {REPLAY_TIMEOUT}s"}
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    report = next((ln.removeprefix("Report -> ") for ln in reversed(lines) if ln.startswith("Report -> ")), None)
    result = {"ok": proc.returncode == 0, "report": report, "summary": lines}
    if proc.returncode != 0:
        result["stderr"] = proc.stderr[-2000:]
    return result
