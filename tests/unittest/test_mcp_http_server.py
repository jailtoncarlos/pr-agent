import pytest

import pr_agent.servers.mcp_http_server as mcp_http_server


def test_parse_args_uses_defaults(monkeypatch):
    monkeypatch.delenv("PR_AGENT_MCP_HTTP_HOST", raising=False)
    monkeypatch.delenv("PR_AGENT_MCP_HTTP_PORT", raising=False)
    monkeypatch.delenv("PR_AGENT_MCP_HTTP_PATH", raising=False)
    monkeypatch.delenv("PR_AGENT_MCP_HTTP_LOG_LEVEL", raising=False)
    monkeypatch.delenv("PR_AGENT_MCP_BEARER_TOKEN", raising=False)

    config = mcp_http_server.parse_args([])

    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.path == "/mcp"
    assert config.log_level == "info"
    assert config.bearer_token is None


def test_parse_args_reads_env_and_normalizes_path(monkeypatch):
    monkeypatch.setenv("PR_AGENT_MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("PR_AGENT_MCP_HTTP_PORT", "3333")
    monkeypatch.setenv("PR_AGENT_MCP_HTTP_PATH", "pr-agent/mcp")
    monkeypatch.setenv("PR_AGENT_MCP_HTTP_LOG_LEVEL", "warning")
    monkeypatch.setenv("PR_AGENT_MCP_BEARER_TOKEN", "secret")

    config = mcp_http_server.parse_args([])

    assert config.host == "0.0.0.0"
    assert config.port == 3333
    assert config.path == "/pr-agent/mcp"
    assert config.log_level == "warning"
    assert config.bearer_token == "secret"


def test_build_app_sets_mcp_http_settings():
    config = mcp_http_server.HttpServerConfig(
        host="127.0.0.1",
        port=3333,
        path="/custom-mcp",
        log_level="debug",
        bearer_token=None,
    )

    app = mcp_http_server.build_app(config)

    assert app is not None
    assert mcp_http_server.mcp.settings.host == "127.0.0.1"
    assert mcp_http_server.mcp.settings.port == 3333
    assert mcp_http_server.mcp.settings.streamable_http_path == "/custom-mcp"


@pytest.mark.asyncio
async def test_bearer_token_middleware_rejects_missing_token():
    async def app(scope, receive, send):
        raise AssertionError("inner app should not be called")

    messages = []
    middleware = mcp_http_server.BearerTokenMiddleware(app, "secret")
    await middleware(
        {"type": "http", "headers": []},
        _receive,
        _send_to(messages),
    )

    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_bearer_token_middleware_allows_matching_token():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = []
    middleware = mcp_http_server.BearerTokenMiddleware(app, "secret")
    await middleware(
        {"type": "http", "headers": [(b"authorization", b"Bearer secret")]},
        _receive,
        _send_to(messages),
    )

    assert called is True
    assert messages[0]["status"] == 204


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _send_to(messages):
    async def _send(message):
        messages.append(message)

    return _send
