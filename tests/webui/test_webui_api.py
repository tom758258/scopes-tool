from fastapi.testclient import TestClient
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
    assert "Scopes Tool WebUI" in root.text
    assert "text/html" in root.headers["content-type"]

    stylesheet = client.get("/static/styles.css")
    script = client.get("/static/app.js")
    assert stylesheet.status_code == 200
    assert script.status_code == 200


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
