from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from .core import dispatch_tool


CAPABILITY_CONTEXT = "sovereign.n8n-ci-evidence-capability.v1"
MASTER_CREDENTIAL_NAME = "n8n-evidence-master.key"
MAX_REQUEST_BODY_BYTES = 4096
EVIDENCE_ROUTE = "/api/v1/n8n/ci-evidence"
SUPPORTED_LANES = frozenset(
    {
        (
            "OuroborosCollective",
            "Sovereign-Studio-ato",
            "sovereign-coordinated-release.yml",
            "main",
        ),
        (
            "OuroborosCollective",
            "Echoes_of_Aurion",
            "340269357",
            "main",
        ),
    }
)


class N8NCIEvidenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    repo: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    workflow_id: StrictInt | StrictStr
    branch: str = Field(default="main", min_length=1, max_length=255)
    previous_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("workflow_id")
    @classmethod
    def validate_workflow_id(cls, value: int | str) -> int | str:
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("workflow_id must be positive")
            return value
        selector = value.strip()
        if selector.isdigit():
            if len(selector) > 20 or int(selector) <= 0:
                raise ValueError("workflow_id numeric selector is invalid")
            return selector
        if len(selector) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", selector):
            raise ValueError("workflow_id must be a safe workflow filename or positive integer")
        return selector

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        branch = value.strip()
        if (
            not branch
            or branch.startswith(("/", "~"))
            or branch.endswith(("/", "."))
            or ".." in branch
            or "//" in branch
            or "@{" in branch
            or any(character.isspace() or character in "\\~^:?*[" for character in branch)
        ):
            raise ValueError("branch is not a safe Git ref")
        return branch


def lane_identity(call: N8NCIEvidenceArgs) -> tuple[str, str, str, str]:
    return call.owner, call.repo, str(call.workflow_id), call.branch


def capability_message(call: N8NCIEvidenceArgs) -> bytes:
    owner, repo, workflow_id, branch = lane_identity(call)
    return (
        f"{CAPABILITY_CONTEXT}\n"
        f"{owner}/{repo}\n"
        f"{workflow_id}\n"
        f"{branch}"
    ).encode("utf-8")


def derive_lane_capability(master_key: str, call: N8NCIEvidenceArgs) -> str:
    return hmac.new(
        master_key.encode("utf-8"),
        capability_message(call),
        hashlib.sha256,
    ).hexdigest()


def read_master_key() -> str:
    credentials_directory = os.getenv("CREDENTIALS_DIRECTORY", "").strip()
    if not credentials_directory or not Path(credentials_directory).is_absolute():
        raise HTTPException(
            status_code=503,
            detail="n8n evidence master credential is not configured",
        )
    path = Path(credentials_directory) / MASTER_CREDENTIAL_NAME
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise HTTPException(
            status_code=503,
            detail="n8n evidence master credential is unavailable",
        ) from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size < 64
            or metadata.st_size > 65
        ):
            raise HTTPException(
                status_code=503,
                detail="n8n evidence master credential is invalid",
            )
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
            master_key = handle.read(66).strip()
    finally:
        os.close(descriptor)
    if not re.fullmatch(r"[0-9a-f]{64}", master_key):
        raise HTTPException(
            status_code=503,
            detail="n8n evidence master credential is invalid",
        )
    return master_key


def check_lane_capability(
    call: N8NCIEvidenceArgs,
    supplied_capability: str | None,
) -> None:
    if lane_identity(call) not in SUPPORTED_LANES:
        raise HTTPException(status_code=403, detail="n8n evidence lane is not permitted")
    master_key = read_master_key()
    expected = derive_lane_capability(master_key, call)
    if not hmac.compare_digest(supplied_capability or "", expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Sovereign-Evidence-Capability",
        )


class EvidenceBodyTooLarge(Exception):
    """Internal signal raised before an oversized request reaches Pydantic."""


class EvidenceBoundaryMiddleware:
    """Authenticate the header shape and cap all body streams before JSON parsing."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("path") != EVIDENCE_ROUTE
            or scope.get("method") != "POST"
        ):
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers") or ())
        capabilities = [
            value
            for name, value in headers
            if name.lower() == b"x-sovereign-evidence-capability"
        ]
        if len(capabilities) != 1 or not re.fullmatch(rb"[0-9a-f]{64}", capabilities[0]):
            await Response(status_code=401)(scope, receive, send)
            return

        content_lengths = [
            value
            for name, value in headers
            if name.lower() == b"content-length"
        ]
        if len(content_lengths) > 1 or (
            content_lengths
            and not re.fullmatch(rb"[0-9]+", content_lengths[0])
        ):
            await Response(status_code=400)(scope, receive, send)
            return
        if content_lengths:
            normalized_length = content_lengths[0].lstrip(b"0") or b"0"
            encoded_limit = str(MAX_REQUEST_BODY_BYTES).encode("ascii")
            if len(normalized_length) > len(encoded_limit) or (
                len(normalized_length) == len(encoded_limit)
                and normalized_length > encoded_limit
            ):
                await Response(status_code=413)(scope, receive, send)
                return

        received_bytes = 0
        response_started = False

        async def bounded_receive() -> dict[str, Any]:
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body") or b"")
                if received_bytes > MAX_REQUEST_BODY_BYTES:
                    raise EvidenceBodyTooLarge
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
        except EvidenceBodyTooLarge:
            if response_started:
                raise
            await Response(status_code=413)(scope, receive, send)


app = FastAPI(
    title="Sovereign n8n CI Evidence",
    version="1.0.0",
    description="Capability-bound, observation-only CI evidence listener.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    redirect_slashes=False,
)
app.add_middleware(EvidenceBoundaryMiddleware)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "sovereign-n8n-ci-evidence",
        "capabilityContext": CAPABILITY_CONTEXT,
    }


def evidence_dispatch_failure_response() -> JSONResponse:
    """Return a constant, secret-safe failure contract for the HTTP adapter."""
    return JSONResponse(
        status_code=502,
        content={
            "ok": False,
            "tool": "github_actions_run_evidence",
            "error": "CI evidence acquisition failed",
        },
    )


@app.post(EVIDENCE_ROUTE)
def n8n_ci_evidence(
    call: N8NCIEvidenceArgs,
    x_sovereign_evidence_capability: str | None = Header(
        default=None,
        alias="X-Sovereign-Evidence-Capability",
    ),
) -> Any:
    check_lane_capability(call, x_sovereign_evidence_capability)
    try:
        outcome = dispatch_tool(
            "github_actions_run_evidence",
            call.model_dump(exclude_none=True),
        )
    except Exception:
        return evidence_dispatch_failure_response()
    if not isinstance(outcome, dict) or outcome.get("ok") is not True:
        return evidence_dispatch_failure_response()
    return outcome
