from fastapi.testclient import TestClient

from api.main import create_app
from api.state import state


def _push(n: int) -> None:
    """Push `n` numbered log entries through the same path the capture manager uses."""
    for i in range(n):
        state.push_log({"level": "info", "message": f"line {i}", "timestamp": "00:00:00"})


def test_tail_returns_last_n_lines(client):
    state.log_tail.clear()
    _push(10)
    body = client.get("/api/capture/log", params={"n": 3}).json()
    assert [e["message"] for e in body["lines"]] == ["line 7", "line 8", "line 9"]


def test_tail_default_and_empty(client):
    state.log_tail.clear()
    assert client.get("/api/capture/log").json()["lines"] == []
    _push(5)
    assert len(client.get("/api/capture/log").json()["lines"]) == 5


def test_tail_buffer_is_bounded(client):
    state.log_tail.clear()
    _push(state.log_tail.maxlen + 20)
    assert len(state.log_tail) == state.log_tail.maxlen
    assert client.get("/api/capture/log", params={"n": 1}).json()["lines"][0]["message"] == f"line {state.log_tail.maxlen + 19}"


def test_push_log_still_feeds_websocket_queue():
    state.log_tail.clear()
    _push(1)
    assert state.log_queue.get_nowait()["message"] == "line 0"


def test_tail_rejects_bad_n(client):
    assert client.get("/api/capture/log", params={"n": 0}).status_code == 422


def test_tail_requires_token():
    c = TestClient(create_app(token="tok"))
    assert c.get("/api/capture/log").status_code == 401
    assert c.get("/api/capture/log", headers={"X-Hub-Token": "tok"}).status_code == 200
