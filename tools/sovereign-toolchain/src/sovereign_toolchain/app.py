from __future__ import annotations

import contextlib
from fastapi import FastAPI
from .api_server import app as rest_app
from .mcp_server import mcp

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
