import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.auth import TokenAuthMiddleware

TOKEN = "s3cret-token"


def _build_app(token: str = TOKEN) -> FastAPI:
    """Small app with one normal route, one asset route and one WebSocket, wrapped in the middleware."""
    app = FastAPI()

    @app.get("/api/thing")
    def thing():
        return {"ok": True}

    @app.get("/assets/pic.png")
    def pic():
        return {"img": True}

    @app.websocket("/ws")
    async def socket(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({"hi": True})
        await websocket.close()

    app.add_middleware(TokenAuthMiddleware, token=token)
    return app


def test_request_without_token_is_rejected():
    r = TestClient(_build_app()).get("/api/thing")
    assert r.status_code == 401
    assert "token" in r.json()["detail"].lower()


def test_request_with_wrong_token_is_rejected():
    r = TestClient(_build_app()).get("/api/thing", headers={"X-Hub-Token": "nope"})
    assert r.status_code == 401


def test_request_with_correct_header_passes():
    r = TestClient(_build_app()).get("/api/thing", headers={"X-Hub-Token": TOKEN})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_request_with_token_in_query_string_passes():
    r = TestClient(_build_app()).get(f"/api/thing?token={TOKEN}")
    assert r.status_code == 200


def test_assets_are_exempt():
    # <img> tags cannot send headers, and the game art is not private.
    r = TestClient(_build_app()).get("/assets/pic.png")
    assert r.status_code == 200


def test_websocket_without_token_is_closed():
    with pytest.raises(WebSocketDisconnect):
        with TestClient(_build_app()).websocket_connect("/ws") as ws:
            ws.receive_json()


def test_websocket_with_token_in_query_string_connects():
    with TestClient(_build_app()).websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert ws.receive_json() == {"hi": True}


def test_empty_token_disables_the_check():
    r = TestClient(_build_app(token="")).get("/api/thing")
    assert r.status_code == 200


def test_real_app_has_the_middleware_installed():
    from api.main import create_app
    assert any(m.cls is TokenAuthMiddleware for m in create_app().user_middleware)


def test_port_comes_from_the_environment(monkeypatch):
    # Tauri picks the port and passes it in, so it never has to read one back off our stdout.
    from api.main import _chosen_port
    monkeypatch.setenv("HUB_CZN_PORT", "7849")
    assert _chosen_port() == 7849


def test_port_falls_back_to_a_free_one_when_unset(monkeypatch):
    from api.main import _chosen_port
    monkeypatch.delenv("HUB_CZN_PORT", raising=False)
    assert 7842 <= _chosen_port() <= 7851


def test_junk_in_the_port_variable_is_ignored(monkeypatch):
    from api.main import _chosen_port
    monkeypatch.setenv("HUB_CZN_PORT", "not-a-port")
    assert 7842 <= _chosen_port() <= 7851
