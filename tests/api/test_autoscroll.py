from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_autoscroll_start_capture_not_running():
    r = client.post("/api/autoscroll/start")
    assert r.status_code == 422


def test_autoscroll_start_already_running():
    from api.state import state
    state.capture_running = True
    state.autoscroll_running = True
    try:
        r = client.post("/api/autoscroll/start")
        assert r.status_code == 409
    finally:
        state.capture_running = False
        state.autoscroll_running = False


def test_autoscroll_start_success():
    from api.state import state
    state.capture_running = True
    try:
        with patch("api.routes.autoscroll.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            r = client.post("/api/autoscroll/start")
            mock_thread.return_value.start.assert_called_once()
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert state.autoscroll_running is True
    finally:
        state.capture_running = False
        state.autoscroll_running = False


def test_autoscroll_stop():
    from api.state import state
    state.autoscroll_running = True
    try:
        r = client.post("/api/autoscroll/stop")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert state.autoscroll_running is False
    finally:
        state.autoscroll_running = False


def _run_loop(pages_by_click, pages_target=50, start_page=None, slow_reads=0, unreadable=False):
    """
    Run the Auto-Scroll loop with the game and the clock faked out.

    Args:
        pages_by_click: The `last_history_page` the rescue file holds after each click, or None when no page arrived.
        pages_target: The most pages to fetch.
        start_page: The `last_history_page` already in the file when the loop starts.
        slow_reads: How many reads after each click still miss its page.
        unreadable: Whether those slow reads find the file mid-write rather than unchanged.

    Returns:
        The number of clicks and the messages broadcast to the UI.
    """
    import sys
    from api.routes import autoscroll
    from api.state import state

    docs = [{"records": [], "last_history_page": start_page} if start_page else {"records": []}]
    for page in pages_by_click:
        docs.append(docs[-1] if page is None else {"records": docs[-1]["records"] + [{}] * 10, "last_history_page": page})
    clicks = []
    reads = [slow_reads]
    clock = [0.0]
    gui = MagicMock()
    gui.click.side_effect = lambda *a: (clicks.append(a), reads.__setitem__(0, 0))

    def read():
        reads[0] += 1
        i = min(len(clicks), len(docs) - 1)
        if reads[0] <= slow_reads:
            return None if unreadable else docs[i - 1]
        return docs[i]

    state.autoscroll_running = True
    try:
        with patch.dict(sys.modules, {"pyautogui": gui}), patch.object(autoscroll, "_read_rescue", read),                 patch.object(autoscroll.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s)),                 patch.object(autoscroll.time, "monotonic", lambda: clock[0]),                 patch.object(autoscroll.manager, "broadcast", new_callable=MagicMock) as broadcast, patch.object(autoscroll.asyncio, "run_coroutine_threadsafe"):
            autoscroll._autoscroll_loop(None, pages_target)
    finally:
        state.autoscroll_running = False
    return len(clicks), [c.args[0] for c in broadcast.call_args_list]


def _page(seq, has_more=True):
    return {"pool": "gacha_card_factor", "has_more": has_more, "seq": seq}


def test_autoscroll_stops_on_the_last_page():
    clicks, sent = _run_loop([_page(2), _page(3), _page(4, has_more=False)], start_page=_page(1))
    assert clicks == 3
    assert sent[-1] == {"type": "autoscroll.done", "pages": 3, "records": 30, "reason": "last_page"}


def test_autoscroll_stops_when_clicks_bring_no_new_page():
    # The cursor is not on the next-page button, so clicking more would only click on whatever is under it.
    clicks, sent = _run_loop([None, None, None], start_page=_page(1))
    assert clicks == 2
    assert sent[-1]["reason"] == "no_page"


def test_autoscroll_on_a_banner_with_one_page_reports_the_last_page():
    _, sent = _run_loop([None, None], start_page=_page(1, has_more=False))
    assert sent[-1]["reason"] == "last_page"


def test_autoscroll_stops_at_the_page_limit():
    clicks, sent = _run_loop([_page(n) for n in range(2, 10)], pages_target=3, start_page=_page(1))
    assert clicks == 3
    assert sent[-1]["reason"] == "max_pages"


def test_autoscroll_only_counts_pages_that_arrived():
    clicks, sent = _run_loop([_page(2), None, _page(3, has_more=False)], start_page=_page(1))
    assert clicks == 3
    assert [m["pages"] for m in sent if m["type"] == "autoscroll.progress"] == [1, 2]


def test_autoscroll_waits_for_a_slow_page():
    clicks, sent = _run_loop([_page(2), _page(3, has_more=False)], start_page=_page(1), slow_reads=4)
    assert clicks == 2
    assert sent[-1]["reason"] == "last_page"


def test_autoscroll_does_not_count_a_half_written_file_as_a_page():
    clicks, sent = _run_loop([None, None], start_page=_page(1), slow_reads=2, unreadable=True)
    assert clicks == 2
    assert sent[-1] == {"type": "autoscroll.done", "pages": 0, "records": 0, "reason": "no_page"}
