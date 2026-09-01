from __future__ import annotations

import contextlib
import hmac
import os
from typing import Any

from fastapi import FastAPI, Response

from .api_server import app as rest_app
from .mcp_server import mcp


class MCPAuthBoundaryMiddleware:
    """Fail closed before any loopback MCP request reaches the tool dispatcher."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = str(scope.get("path") or "")
        if scope.get("type") == "http" and (path == "/mcp" or path.startswith("/mcp/")):
            expected = os.getenv("TOOLCHAIN_API_KEY", "").strip()
            if not expected or not expected.isascii():
                await Response(status_code=503)(scope, receive, send)
                return
            supplied_values = [
                value
                for name, value in list(scope.get("headers") or ())
                if name.lower() == b"x-toolchain-key"
            ]
            expected_bytes = expected.encode("ascii")
            if (
                len(supplied_values) != 1
                or not hmac.compare_digest(supplied_values[0], expected_bytes)
            ):
                await Response(status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield


app = FastAPI(
    title="Sovereign Universal Toolchain Hybrid Server",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(MCPAuthBoundaryMiddleware)

app.mount("/api", rest_app)
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/")
def root():
    return {
        "ok": True,
        "name": "Sovereign Universal Toolchain",
        "rest": "/api/v1/manifest",
        "openapi": "/api/openapi.json",
        "mcp": "/mcp",
    }
