def test_about_returns_version(client):
    from hub_czn_version import __version__
    response = client.get("/api/about")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__


def test_about_returns_github_urls(client):
    # These drive the About page's links. Pointing them at upstream would send people to upstream's
    # releases rather than the ones this fork builds.
    response = client.get("/api/about")
    assert response.status_code == 200
    body = response.json()
    assert body["github_url"] == "https://github.com/steve1316/hub-czn-updated"
    assert body["releases_url"] == "https://github.com/steve1316/hub-czn-updated/releases"
    assert body["issues_url"] == "https://github.com/steve1316/hub-czn-updated/issues"
