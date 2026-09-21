from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = "_wolfram_source_intelligence_test"


def _install_package(name: str, path: Path) -> None:
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules[name] = package


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_install_package(_PACKAGE, ROOT / "backend" / "agent_runtime")
_install_package(f"{_PACKAGE}.adapters", ROOT / "backend" / "agent_runtime" / "adapters")
_load(
    f"{_PACKAGE}.adapters.wolfram_agenttools",
    ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_agenttools.py",
)
source = _load(
    f"{_PACKAGE}.wolfram_source_intelligence",
    ROOT / "backend" / "agent_runtime" / "wolfram_source_intelligence.py",
)


def _receipt(normalized_result: str):
    return SimpleNamespace(
        normalized_result=normalized_result,
        request_hash="a" * 64,
        response_hash="b" * 64,
        request_id="request-1",
        response_uuid="uuid-1",
    )


@pytest.mark.parametrize(
    ("operation", "expected_symbol"),
    [
        ("parse", 'PacletSymbol["CodeParser","CodeParse"]'),
        ("inspect", 'PacletSymbol["CodeInspector","CodeInspect"]'),
        ("format_preview", 'PacletSymbol["CodeFormatter","CodeFormat"]'),
    ],
)
def test_source_is_encoded_as_data_never_embedded_as_executable_code(operation, expected_symbol):
    dangerous = 'RunProcess[{"sh","-c","touch /tmp/should-not-run"}]'
    expression, source_sha256, source_bytes = source.build_wolfram_source_expression(
        operation, dangerous
    )

    assert dangerous not in expression
    assert "RunProcess" not in expression
    assert "BaseDecode" in expression
    assert expected_symbol in expression
    assert source_sha256 == hashlib.sha256(dangerous.encode("utf-8")).hexdigest()
    assert source_bytes == len(dangerous.encode("utf-8"))


def test_parse_returns_revision_bound_static_evidence_without_runtime_claim():
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)
        return _receipt(
            '{"operation":"parse","astHash":"'
            + "c" * 64
            + '","leafCount":19,"astPreview":"ContainerNode[...]","wolframVersion":"15.0.1",'
            '"codeParserVersion":"1.13","codeInspectorVersion":"1.13","codeFormatterVersion":"1.13"}'
        )

    result = source.run_wolfram_source_intelligence(
        operation="parse", source="1+1", executor=executor
    )

    assert result["ok"] is True
    assert result["status"] == "WOLFRAM_SOURCE_INTELLIGENCE_SUCCEEDED_UNVERIFIED"
    assert result["sourceExecuted"] is False
    assert result["sourceEgressOccurred"] is True
    assert result["runtimeVerified"] is False
    assert result["mutationPerformed"] is False
    assert result["secretValuesReturned"] is False
    assert result["providerEvidence"]["capabilityId"] == "wolfram.cag.compute"
    assert calls[0]["payload"]["timeConstraint"] == 20


def test_inspector_preserves_structured_findings():
    payload = (
        '{"operation":"inspect","count":1,"truncated":false,"issues":['
        '{"tag":"DuplicateClauses","description":"same","severity":"Warning",'
        '"source":[[1,6],[1,7]],"confidence":0.95}],'
        '"wolframVersion":"15.0.1","codeParserVersion":"1.13",'
        '"codeInspectorVersion":"1.13","codeFormatterVersion":"1.13"}'
    )
    result = source.run_wolfram_source_intelligence(
        operation="inspect",
        source="If[a,b,b]",
        executor=lambda **_kwargs: _receipt(payload),
    )

    assert result["ok"] is True
    assert result["result"]["issues"][0]["tag"] == "DuplicateClauses"
    assert result["result"]["issues"][0]["confidence"] == 0.95


def test_format_preview_is_safe_to_apply_only_when_parser_structure_matches():
    safe_payload = (
        '{"operation":"format_preview","structuralEqual":true,"formatChanged":true,'
        '"originalAstHash":"' + "d" * 64 + '","formattedAstHash":"' + "d" * 64 + '",'
        '"formattedSource":"If[a,\\n    b,\\n    c\\n]",'
        '"wolframVersion":"15.0.1","codeParserVersion":"1.13",'
        '"codeInspectorVersion":"1.13","codeFormatterVersion":"1.13"}'
    )
    safe = source.run_wolfram_source_intelligence(
        operation="format_preview",
        source="If[a,b,c]",
        executor=lambda **_kwargs: _receipt(safe_payload),
    )
    assert safe["ok"] is True
    assert safe["result"]["safeToApply"] is True
    assert safe["result"]["formattedSourceSha256"] == hashlib.sha256(
        safe["result"]["formattedSource"].encode("utf-8")
    ).hexdigest()

    drift_payload = safe_payload.replace('"structuralEqual":true', '"structuralEqual":false')
    drift = source.run_wolfram_source_intelligence(
        operation="format_preview",
        source="If[a,b,c]",
        executor=lambda **_kwargs: _receipt(drift_payload),
    )
    assert drift["ok"] is False
    assert drift["status"] == "WOLFRAM_SOURCE_FORMAT_DRIFT_DETECTED"
    assert drift["result"]["safeToApply"] is False


def test_invalid_operation_and_oversize_source_fail_closed():
    with pytest.raises(source.WolframSourceIntelligenceError, match="unknown"):
        source.build_wolfram_source_expression("execute", "1+1")
    with pytest.raises(source.WolframSourceIntelligenceError, match="32768"):
        source.build_wolfram_source_expression(
            "parse", "x" * (source.MAX_WOLFRAM_SOURCE_BYTES + 1)
        )


def test_canonical_and_shipping_source_intelligence_are_byte_equal():
    canonical = (ROOT / "backend" / "agent_runtime" / "wolfram_source_intelligence.py").read_bytes()
    mirror = (
        ROOT
        / "scripts"
        / "sovereign-backend"
        / "agent_runtime"
        / "wolfram_source_intelligence.py"
    ).read_bytes()
    assert canonical == mirror
