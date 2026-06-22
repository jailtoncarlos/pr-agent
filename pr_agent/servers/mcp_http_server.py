"""Streamable HTTP MCP server for PR-Agent.

This entry point is intended for MCP clients that cannot spawn a local stdio
process, such as hosted or desktop app connectors. The existing
``pr-agent-mcp`` command remains the recommended path for local developer
agents that support stdio.
"""
from __future__ import annotations

import argparse
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import uvicorn
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

try:
    from pr_agent.servers.mcp_server import mcp
except ImportError as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        "The PR-Agent MCP HTTP server needs the 'mcp' package. Install it with:\n"
        '    pip install "pr-agent[mcp]"'
    ) from exc


@dataclass(frozen=True)
class HttpServerConfig:
    host: str
    port: int
    path: str
    log_level: str
    bearer_token: str | None


class BearerTokenMiddleware:
    """Require ``Authorization: Bearer <token>`` for HTTP requests."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        expected = f"Bearer {self.token}".encode()
        headers = dict(scope.get("headers") or [])
        if headers.get(b"authorization") != expected:
            response = PlainTextResponse(
                "Missing or invalid bearer token.",
                status_code=HTTPStatus.UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _normalize_path(path: str) -> str:
    path = path.strip() or "/mcp"
    return path if path.startswith("/") else f"/{path}"


def parse_args(argv: list[str] | None = None) -> HttpServerConfig:
    parser = argparse.ArgumentParser(
        description="Run PR-Agent's MCP tools over Streamable HTTP.",
    )
    parser.add_argument("--host", default=_env("PR_AGENT_MCP_HTTP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(_env("PR_AGENT_MCP_HTTP_PORT", "8000")))
    parser.add_argument("--path", default=_env("PR_AGENT_MCP_HTTP_PATH", "/mcp"))
    parser.add_argument("--log-level", default=_env("PR_AGENT_MCP_HTTP_LOG_LEVEL", "info"))
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get("PR_AGENT_MCP_BEARER_TOKEN"),
        help="Optional bearer token required on incoming HTTP requests.",
    )
    args = parser.parse_args(argv)
    return HttpServerConfig(
        host=args.host,
        port=args.port,
        path=_normalize_path(args.path),
        log_level=args.log_level,
        bearer_token=args.bearer_token,
    )


def build_app(config: HttpServerConfig) -> ASGIApp:
    mcp.settings.host = config.host
    mcp.settings.port = config.port
    mcp.settings.streamable_http_path = config.path

    app: ASGIApp = mcp.streamable_http_app()
    if config.bearer_token:
        app = BearerTokenMiddleware(app, config.bearer_token)
    return app


def main(argv: list[str] | None = None, run_server: Callable[..., Any] | None = None) -> None:
    """Console entry point (``pr-agent-mcp-http``)."""
    config = parse_args(argv)
    app = build_app(config)
    runner = run_server or uvicorn.run
    runner(app, host=config.host, port=config.port, log_level=config.log_level)


if __name__ == "__main__":
    main()
