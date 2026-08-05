from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

SUPPLEMENTAL_ONLY = "SUPPLEMENTAL_ONLY"


class WolframAdapterStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE_READ_ONLY = "AVAILABLE_READ_ONLY"
    SUCCEEDED_UNVERIFIED = "SUCCEEDED_UNVERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class WolframCapability:
    capability_id: str
    tool_name: str
    read_only: bool


WOLFRAM_CAPABILITY_MAP: Mapping[str, WolframCapability] = {
    "wolfram.context.search": WolframCapability("wolfram.context.search", "WolframContext", True),
    "wolfram.alpha.query": WolframCapability("wolfram.alpha.query", "WolframAlpha", True),
    "wolfram.language.inspect": WolframCapability("wolfram.language.inspect", "CodeInspector", True),
    "wolfram.tests.read": WolframCapability("wolfram.tests.read", "TestReport", True),
    "wolfram.symbol.read": WolframCapability("wolfram.symbol.read", "SymbolDefinition", True),
    "wolfram.notebook.read": WolframCapability("wolfram.notebook.read", "ReadNotebook", True),
}

_FORBIDDEN_TOOLS = {
    "WriteNotebook",
    "WolframLanguageEvaluator",
    "PacletInstall",
    "PacletUpdate",
    "RunProcess",
    "StartProcess",
}


@dataclass(frozen=True, slots=True)
class WolframAdapterAttestation:
    installation_revision: str
    mcp_server_identity_hash: str
    paclet_version: str
    wolfram_version: str
    runtime_mode: str
    input_schema_hash: str
    output_schema_hash: str
    license_attested: bool

    def is_read_only_ready(self) -> bool:
        return all(
            (
                self.installation_revision,
                self.mcp_server_identity_hash,
                self.paclet_version,
                self.wolfram_version,
                self.input_schema_hash,
                self.output_schema_hash,
            )
        ) and self.license_attested and self.runtime_mode in {"LocalReadOnly", "CloudReadOnly"}


def authorize_wolfram_tool(
    *,
    capability_id: str,
    requested_tool_name: str,
    attestation: WolframAdapterAttestation | None,
) -> WolframAdapterStatus:
    """Authorize an explicit read-only mapping; names never imply capability."""
    if requested_tool_name in _FORBIDDEN_TOOLS:
        return WolframAdapterStatus.BLOCKED
    capability = WOLFRAM_CAPABILITY_MAP.get(capability_id)
    if capability is None or capability.tool_name != requested_tool_name or not capability.read_only:
        return WolframAdapterStatus.BLOCKED
    if attestation is None or not attestation.is_read_only_ready():
        return WolframAdapterStatus.UNAVAILABLE
    return WolframAdapterStatus.AVAILABLE_READ_ONLY


def normalize_wolfram_result(result_hash: str, summary: str) -> dict[str, str]:
    if not result_hash or not summary:
        raise ValueError("result hash and bounded summary are required")
    return {
        "adapterMode": SUPPLEMENTAL_ONLY,
        "status": WolframAdapterStatus.SUCCEEDED_UNVERIFIED.value,
        "resultHash": result_hash,
        "summary": summary,
        "truthNotice": "Wolfram output is supplemental and cannot verify repository, runtime, deployment, ARE or Kappa truth.",
    }
