"""Bounded Wolfram Language source intelligence over the existing CAG compute transport.

The supplied source is always treated as data. It is base64 encoded before it
is embedded in one of three fixed Wolfram Language expressions and is only
passed to CodeParser, CodeInspector or CodeFormatter. The source itself is
never evaluated as Wolfram Language code.

Provider success remains SUCCEEDED_UNVERIFIED. Static source analysis cannot
prove repository state, deployment state, runtime state, ARE/Kappa truth or the
semantic correctness of arbitrary programs.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Callable

from .adapters.wolfram_agenttools import execute_live_cag_request


MAX_WOLFRAM_SOURCE_BYTES = 32 * 1024
WOLFRAM_SOURCE_OPERATIONS = frozenset({"parse", "inspect", "format_preview"})
WOLFRAM_CODETOOLS_REFERENCE_REVISIONS = {
    "CodeParser": "8c6f94947181884b3d6f14a69857d6a01404d1fc",
    "CodeInspector": "3f1d5935b9b81c61bf92b78cd0dc68044abe13d7",
    "CodeFormatter": "023922634ebf3ac93d35baacad54208b4fbaaa0d",
}


class WolframSourceIntelligenceError(ValueError):
    pass


def _encode_source(source: str) -> tuple[str, str, int]:
    if not isinstance(source, str) or not source:
        raise WolframSourceIntelligenceError("source must be a non-empty string")
    if "\x00" in source:
        raise WolframSourceIntelligenceError("source contains a forbidden NUL byte")
    raw = source.encode("utf-8")
    if len(raw) > MAX_WOLFRAM_SOURCE_BYTES:
        raise WolframSourceIntelligenceError("source exceeds the 32768-byte limit")
    return (
        base64.b64encode(raw).decode("ascii"),
        hashlib.sha256(raw).hexdigest(),
        len(raw),
    )


def _metadata_fields() -> str:
    return (
        '"wolframVersion"->$Version,'
        '"codeParserVersion"->Quiet@Check[PacletObject["CodeParser"]["Version"],"UNAVAILABLE"],'
        '"codeInspectorVersion"->Quiet@Check[PacletObject["CodeInspector"]["Version"],"UNAVAILABLE"],'
        '"codeFormatterVersion"->Quiet@Check[PacletObject["CodeFormatter"]["Version"],"UNAVAILABLE"]'
    )


def build_wolfram_source_expression(operation: str, source: str) -> tuple[str, str, int]:
    selected = str(operation or "").strip()
    if selected not in WOLFRAM_SOURCE_OPERATIONS:
        raise WolframSourceIntelligenceError("unknown Wolfram source-intelligence operation")
    encoded, source_sha256, source_bytes = _encode_source(source)
    prefix = (
        'With[{s=FromCharacterCode[Normal@BaseDecode["'
        + encoded
        + '"],"UTF8"]},'
    )
    metadata = _metadata_fields()

    if selected == "parse":
        body = (
            'Module[{a,n,t},'
            'a=PacletSymbol["CodeParser","CodeParse"][s];'
            'n=a/.assoc_Association:><||>;'
            't=ToString[InputForm[n]];'
            'ExportString[<|'
            '"operation"->"parse",'
            '"astHash"->Hash[t,"SHA256","HexString"],'
            '"leafCount"->LeafCount[n],'
            '"astPreview"->StringTake[ToString[InputForm[a]],UpTo[8000]],'
            + metadata
            + '|>,"RawJSON","Compact"->True]]'
        )
    elif selected == "inspect":
        body = (
            'Module[{items,rows},'
            'items=PacletSymbol["CodeInspector","CodeInspect"][s];'
            'rows=items/.CodeInspector`InspectionObject[tag_,desc_,sev_,data_Association]:>'
            '<|"tag"->tag,"description"->desc,"severity"->sev,'
            '"source"->Lookup[data,CodeParser`Source,Null],'
            '"confidence"->Lookup[data,ConfidenceLevel,Null]|>;'
            'ExportString[<|'
            '"operation"->"inspect",'
            '"count"->Length[rows],'
            '"truncated"->(Length[rows]>100),'
            '"issues"->Take[rows,UpTo[100]],'
            + metadata
            + '|>,"RawJSON","Compact"->True]]'
        )
    else:
        body = (
            'Module[{f,b,a,strip,bn,an},'
            'f=PacletSymbol["CodeFormatter","CodeFormat"][s];'
            'b=PacletSymbol["CodeParser","CodeParse"][s];'
            'a=PacletSymbol["CodeParser","CodeParse"][f];'
            'strip[x_]:=x/.assoc_Association:><||>;'
            'bn=ToString[InputForm[strip[b]]];'
            'an=ToString[InputForm[strip[a]]];'
            'ExportString[<|'
            '"operation"->"format_preview",'
            '"structuralEqual"->SameQ[bn,an],'
            '"formatChanged"->UnsameQ[s,f],'
            '"originalAstHash"->Hash[bn,"SHA256","HexString"],'
            '"formattedAstHash"->Hash[an,"SHA256","HexString"],'
            '"formattedSource"->f,'
            + metadata
            + '|>,"RawJSON","Compact"->True]]'
        )
    return prefix + body + "]", source_sha256, source_bytes


def _decode_provider_json(value: str) -> dict[str, Any]:
    current: Any = str(value or "").strip()
    for _ in range(2):
        if not isinstance(current, str):
            break
        try:
            current = json.loads(current)
        except json.JSONDecodeError as exc:
            raise WolframSourceIntelligenceError(
                "Wolfram source-intelligence result is not valid JSON"
            ) from exc
    if not isinstance(current, dict):
        raise WolframSourceIntelligenceError(
            "Wolfram source-intelligence result is not an object"
        )
    return current


def _hash_optional(value: str) -> str:
    selected = str(value or "")
    return hashlib.sha256(selected.encode("utf-8")).hexdigest() if selected else ""


def run_wolfram_source_intelligence(
    *,
    operation: str,
    source: str,
    executor: Callable[..., Any] = execute_live_cag_request,
) -> dict[str, Any]:
    code, source_sha256, source_bytes = build_wolfram_source_expression(operation, source)
    receipt = executor(
        capability_id="wolfram.cag.compute",
        payload={"code": code, "maxChars": 131072, "timeConstraint": 20},
        normalized_result_limit=128 * 1024,
    )
    result = _decode_provider_json(str(receipt.normalized_result or ""))

    formatted_source = result.get("formattedSource")
    if isinstance(formatted_source, str):
        result["formattedSourceSha256"] = hashlib.sha256(
            formatted_source.encode("utf-8")
        ).hexdigest()

    safe_to_apply = (
        operation == "format_preview"
        and result.get("structuralEqual") is True
        and isinstance(formatted_source, str)
    )
    if operation == "format_preview":
        result["safeToApply"] = safe_to_apply

    ok = not (operation == "format_preview" and not safe_to_apply)
    status = (
        "WOLFRAM_SOURCE_INTELLIGENCE_SUCCEEDED_UNVERIFIED"
        if ok
        else "WOLFRAM_SOURCE_FORMAT_DRIFT_DETECTED"
    )
    return {
        "ok": ok,
        "status": status,
        "operation": operation,
        "sourceSha256": source_sha256,
        "sourceBytes": source_bytes,
        "result": result,
        "providerEvidence": {
            "capabilityId": "wolfram.cag.compute",
            "requestHash": str(receipt.request_hash or ""),
            "responseHash": str(receipt.response_hash or ""),
            "requestIdSha256": _hash_optional(str(receipt.request_id or "")),
            "responseUuidSha256": _hash_optional(str(receipt.response_uuid or "")),
        },
        "reviewedUpstreamReferenceRevisions": dict(WOLFRAM_CODETOOLS_REFERENCE_REVISIONS),
        "sourceExecuted": False,
        "sourceEgressOccurred": True,
        "mutationPerformed": False,
        "runtimeVerified": False,
        "secretValuesReturned": False,
        "truthNotice": (
            "Wolfram CodeTools output is external static-analysis evidence only. "
            "It does not verify repository, deployment, runtime, ARE or Kappa truth."
        ),
    }


__all__ = [
    "MAX_WOLFRAM_SOURCE_BYTES",
    "WOLFRAM_CODETOOLS_REFERENCE_REVISIONS",
    "WOLFRAM_SOURCE_OPERATIONS",
    "WolframSourceIntelligenceError",
    "build_wolfram_source_expression",
    "run_wolfram_source_intelligence",
]
