from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .core import TOOL_DEFINITIONS, briefing, dispatch_tool, safe_error

class ToolCall(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


def check_api_key(x_toolchain_key: str | None = Header(default=None)) -> None:
    """Fail closed for every authenticated route on the loopback-only full app."""
    expected = os.getenv("TOOLCHAIN_API_KEY", "").strip()
    if not expected or not expected.isascii():
        raise HTTPException(status_code=503, detail="toolchain API capability is not configured")
    supplied = x_toolchain_key or ""
    if not supplied.isascii() or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Toolchain-Key")

app = FastAPI(
    title="Sovereign Universal Toolchain",
    version="1.0.0",
    description="Reusable REST/OpenAPI interface for Sovereign repo, sandbox and guarded patch workflows.",
)

@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "sovereign-universal-toolchain"}

@app.get("/v1/manifest")
def manifest() -> dict[str, Any]:
    return {"name": "Sovereign Universal Toolchain", "tools": TOOL_DEFINITIONS}

@app.get("/v1/briefing")
def get_briefing(include_rules: bool = True) -> dict[str, Any]:
    return briefing(include_rules)

@app.post("/v1/tools/{name}")
def invoke_tool(name: str, call: ToolCall, x_toolchain_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_api_key(x_toolchain_key)
    try:
        return dispatch_tool(name, call.args)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        return {"ok": False, "tool": name, "error": safe_error(e)}


@app.post("/v1/github/read-file")
def read_file(call: ToolCall, x_toolchain_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_api_key(x_toolchain_key)
    return dispatch_tool("github_read_file", call.args)

@app.post("/v1/github/apply-search-replace-pr")
def apply_search_replace(call: ToolCall, x_toolchain_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_api_key(x_toolchain_key)
    return dispatch_tool("github_apply_search_replace_pr", call.args)

@app.post("/v1/patch-worker/apply")
def patch_worker(call: ToolCall, x_toolchain_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_api_key(x_toolchain_key)
    return dispatch_tool("apply_patch_worker", call.args)

@app.post("/v1/sovereign/apply-backend-guardrails-pr")
def guardrails_pr(call: ToolCall, x_toolchain_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_api_key(x_toolchain_key)
    return dispatch_tool("apply_backend_guardrails_patch_pr", call.args)
