from fastapi.testclient import TestClient
import re
import uvicorn

from scopes_tool_webui import __version__
from scopes_tool_webui.app import app
from scopes_tool_webui import server


def test_health_identity_and_root_static_serving() -> None:
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "package": "scopes-tool-webui",
        "version": __version__,
    }

    root = client.get("/")
    assert root.status_code == 200
    assert '<title data-i18n="page.title">' in root.text
    assert "text/html" in root.headers["content-type"]

    stylesheet = client.get("/static/styles.css")
    script = client.get("/static/app.js")
    assert stylesheet.status_code == 200
    assert script.status_code == 200


def test_webui_assets_prevent_stale_browser_caching() -> None:
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert root.headers["Cache-Control"] == "no-store"
    versioned_urls = re.findall(r"/static/(?:styles\.css|app\.js)\?v=\d+", root.text)
    assert len(versioned_urls) == 2
    for url in versioned_urls:
        asset = client.get(url)
        assert asset.status_code == 200
        assert asset.headers["Cache-Control"] == "no-store"

    module = client.get("/static/command-form.js")
    assert module.status_code == 200
    assert module.headers["Cache-Control"] == "no-store"

    editor_bootstrap = client.get("/static/editor-bootstrap.js")
    assert editor_bootstrap.status_code == 200
    assert editor_bootstrap.headers["Cache-Control"] == "no-store"


def test_standalone_server_uses_fixed_loopback_default(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, *, host, port: calls.append((host, port)),
    )

    assert server.main([]) == 0
    assert server.main(["--port", "8030"]) == 0
    assert calls == [("127.0.0.1", 8025), ("127.0.0.1", 8030)]


def test_offline_help_routes_are_local_and_no_store():
    client = TestClient(app)
    for name, lang in (("webui.html", "en"), ("webui.zh-TW.html", "zh-TW"),
                       ("supported-models.html", "en"), ("supported-models.zh-TW.html", "zh-TW")):
        response = client.get(f"/static/help/{name}?theme=dark")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert "text/html" in response.headers["content-type"]
        assert f'<html lang="{lang}">' in response.text
    css = client.get("/static/help/help.css")
    assert css.status_code == 200 and css.headers["Cache-Control"] == "no-store"
    assert client.get("/static/help/missing.html").status_code == 404
    assert client.get("/static/help/%2e%2e/%2e%2e/%2e%2e/pyproject.toml").status_code == 404
