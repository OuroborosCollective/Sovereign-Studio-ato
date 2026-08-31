from __future__ import annotations

import hmac
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .core import TOOL_DEFINITIONS, briefing, dispatch_tool, safe_error

class ToolCall(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)

def check_api_key(x_toolchain_key: str | None = Header(default=None)) -> None:
    # Optional shared-secret gate for the legacy/general no-code surface.
    import os
    expected = os.getenv("TOOLCHAIN_API_KEY", "").strip()
    if expected and not hmac.compare_digest(x_toolchain_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Toolchain-Key")


def check_n8n_evidence_key(x_n8n_evidence_key: str | None = Header(default=None)) -> None:
    """Fail-closed capability key for n8n observation-only endpoints."""
    import os
    expected = os.getenv("N8N_EVIDENCE_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="n8n evidence capability is not configured")
    if not hmac.compare_digest(x_n8n_evidence_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-N8N-Evidence-Key")

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

# No-code friendly aliases. These endpoints all accept {"args": {...}} for simple HTTP-request nodes.
@app.post("/v1/n8n/ci-evidence")
def n8n_ci_evidence(call: ToolCall, x_n8n_evidence_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_n8n_evidence_key(x_n8n_evidence_key)
    return dispatch_tool("github_actions_run_evidence", call.args)


@app.post("/v1/n8n/revision-guardian")
def n8n_revision_guardian(call: ToolCall, x_n8n_evidence_key: str | None = Header(default=None)) -> dict[str, Any]:
    check_n8n_evidence_key(x_n8n_evidence_key)
    return dispatch_tool("sovereign_revision_guardian_receipt", call.args)


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
