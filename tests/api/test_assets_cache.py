from fastapi.testclient import TestClient

from api.main import create_app


def test_assets_have_cache_control():
    """Static art is served with a one day public cache header."""
    client = TestClient(create_app(token=""))
    res = client.get("/assets/cards/abnormal_curse_00003.webp")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "public, max-age=86400"


def test_missing_asset_has_no_cache_header():
    """A 404 must not be cached for a day."""
    client = TestClient(create_app(token=""))
    res = client.get("/assets/does_not_exist.png")
    assert res.status_code == 404
    assert "max-age=86400" not in res.headers.get("cache-control", "")
