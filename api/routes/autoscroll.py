from __future__ import annotations

import asyncio
import json
import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.state import state
from api.routes.rescue import _latest_rescue_file
from api.routes.ws import manager

router = APIRouter()
_start_lock = threading.Lock()
# How long to wait after a click before looking for its page, and how long a slow page is still waited for.
PAGE_WAIT_SECONDS = 2.0
PAGE_TIMEOUT_SECONDS = 5.0
POLL_SECONDS = 0.25
# Clicks in a row that bring no new page before giving up. Either the last page is showing or the cursor is not on the button.
MAX_MISSED_CLICKS = 2


class _StartBody(BaseModel):
    pages_count: int = 200


def _read_rescue() -> dict | None:
    """The most recent rescue file, an empty document when there is none, or None when it cannot be read, such as mid-write."""
    path = _latest_rescue_file()
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _page_seq(doc: dict) -> int | None:
    """The counter of the last history page saved in a rescue document, or None before any."""
    return (doc.get("last_history_page") or {}).get("seq")


def _wait_for_page(seq: int | None) -> dict | None:
    """
    Wait for a history page newer than the one already saved.

    Args:
        seq: The counter of the page saved before the click.

    Returns:
        The rescue document once the new page is in it, or None when none arrived in time.
    """
    deadline = time.monotonic() + PAGE_TIMEOUT_SECONDS
    time.sleep(PAGE_WAIT_SECONDS)
    while True:
        doc = _read_rescue()
        if doc is not None and _page_seq(doc) != seq:
            return doc
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_SECONDS)


def _autoscroll_loop(loop: asyncio.AbstractEventLoop, pages_target: int) -> None:
    """
    Click the game's next-page button until the server says there are no more pages.

    Each click is counted only once its page has arrived, which the rescue file shows through `last_history_page`.

    Args:
        loop: The event loop the UI broadcasts run on.
        pages_target: The most pages to fetch, as a safety limit.
    """
    import pyautogui

    for i in range(5, 0, -1):
        if not state.autoscroll_running:
            return
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "autoscroll.countdown", "seconds": i}),
            loop,
        )
        time.sleep(1)

    pos = pyautogui.position()
    doc = _read_rescue() or {}
    has_more = (doc.get("last_history_page") or {}).get("has_more")
    pages = 0
    misses = 0

    while state.autoscroll_running and pages < pages_target and misses < MAX_MISSED_CLICKS:
        pyautogui.click(pos.x, pos.y)
        arrived = _wait_for_page(_page_seq(doc))
        if arrived is None:
            misses += 1
            continue
        misses = 0
        doc = arrived
        has_more = doc["last_history_page"].get("has_more")
        pages += 1
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "autoscroll.progress", "pages": pages, "target": pages_target, "records": len(doc.get("records", []))}),
            loop,
        )
        if has_more is False:
            break

    reason = "last_page" if has_more is False else "no_page" if misses >= MAX_MISSED_CLICKS else "max_pages"
    records = len(doc.get("records", []))
    if state.autoscroll_running:
        state.autoscroll_running = False
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "autoscroll.done", "pages": pages, "records": records, "reason": reason}),
            loop,
        )
    else:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "autoscroll.stopped", "pages": pages, "records": records}),
            loop,
        )


@router.post("/autoscroll/start")
async def autoscroll_start(body: _StartBody = _StartBody()):
    if not state.capture_running:
        raise HTTPException(status_code=422, detail="Capture must be running")
    with _start_lock:
        if state.autoscroll_running:
            raise HTTPException(status_code=409, detail="Auto-scroll already running")
        state.autoscroll_running = True
    loop = asyncio.get_running_loop()
    threading.Thread(target=_autoscroll_loop, args=(loop, max(1, body.pages_count)), daemon=True).start()
    return {"ok": True}


@router.post("/autoscroll/stop")
async def autoscroll_stop():
    state.autoscroll_running = False
    return {"ok": True}
