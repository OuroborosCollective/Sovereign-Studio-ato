from __future__ import annotations

from pathlib import Path
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = ROOT / "backend" / "agent_runtime" / "wolfram_cag_partner_ledger.py"
_SPEC = importlib.util.spec_from_file_location("wolfram_cag_partner_ledger_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
ledger = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ledger)

PartnerAnalysisError = ledger.PartnerAnalysisError
build_partner_analysis_record = ledger.build_partner_analysis_record
persist_partner_analysis = ledger.persist_partner_analysis
public_partner_projection = ledger.public_partner_projection
SHA_A = "a" * 64
SHA_B = "b" * 64
REV = "c" * 40


def _record(**overrides):
    values = {
        "component": "WolframLanguageComputation",
        "normalized_question": '{"code":"2+2"}',
        "normalized_input_sha256": SHA_A,
        "provider_response_sha256": SHA_B,
        "credential_fingerprint_sha256": "d" * 64,
        "verdict": "INCONCLUSIVE",
        "derived_conclusion": "Transport and schema canary succeeded; no semantic claim was evaluated.",
        "repository_revision": REV,
        "runtime_revision": REV,
        "provider_request_id": "request-1",
        "provider_response_uuid": "uuid-1",
        "documentation_class": "PARTNER_REPORTABLE",
        "limitations": ["Provider success is not runtime verification."],
        "source_refs": ["wolfram-official-cag-v1-contract"],
        "created_at": "2026-08-21T20:00:00Z",
    }
    values.update(overrides)
    return build_partner_analysis_record(**values)


def test_created_at_is_metadata_not_causal_identity():
    first = _record(created_at="2026-08-21T20:00:00Z")
    second = _record(created_at="2026-08-22T20:00:00Z")
    assert first["analysisRecordSha256"] == second["analysisRecordSha256"]
    assert first["analysisId"] == second["analysisId"]
    assert first["createdAt"] != second["createdAt"]


def test_secret_shaped_material_is_rejected():
    with pytest.raises(PartnerAnalysisError, match="secret-shaped"):
        _record(derived_conclusion="Authorization: forbidden-secret-value")


def test_supported_or_contradicted_requires_provider_evidence():
    with pytest.raises(PartnerAnalysisError, match="requires provider evidence"):
        _record(verdict="SUPPORTED", provider_response_sha256=None)
    with pytest.raises(PartnerAnalysisError, match="requires provider evidence"):
        _record(verdict="CONTRADICTED", provider_response_sha256=None)


def test_hf_verified_requires_target_readback():
    with pytest.raises(PartnerAnalysisError, match="requires publication and target readback"):
        _record(documentation_class="HF_PUBLISHED_VERIFIED")

    record = _record(
        documentation_class="HF_PUBLISHED_VERIFIED",
        hf_publication_ref="Thorsu/sovereign-evidence-observatory:batch-1",
        hf_target_revision="target-revision-1",
    )
    assert record["documentationClass"] == "HF_PUBLISHED_VERIFIED"


def test_partner_projection_removes_credential_fingerprint():
    record = _record()
    public = public_partner_projection(record)
    assert "credentialFingerprintSha256" not in public
    assert public["analysisRecordSha256"] == record["analysisRecordSha256"]


class _Cursor:
    def __init__(self):
        self.calls = []
        self.closed = False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_persistence_writes_only_normalized_secret_free_record():
    connection = _Connection()
    record = _record()
    analysis_id = persist_partner_analysis(connection, record)
    assert analysis_id == record["analysisId"]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.cursor_instance.closed is True
    sql, params = connection.cursor_instance.calls[0]
    assert "ON CONFLICT (record_sha256) DO NOTHING" in sql
    rendered = repr(params)
    assert "Authorization:" not in rendered
    assert "credentialFingerprintSha256" not in rendered


def test_canonical_and_deployment_mirrors_match_byte_for_byte():
    canonical = (ROOT / "backend" / "agent_runtime" / "wolfram_cag_partner_ledger.py").read_bytes()
    mirror = (ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_partner_ledger.py").read_bytes()
    assert canonical == mirror

    migration = (ROOT / "backend" / "migrations" / "058_wolfram_cag_partner_analysis.sql").read_bytes()
    migration_mirror = (ROOT / "scripts" / "sovereign-backend" / "migrations" / "058_wolfram_cag_partner_analysis.sql").read_bytes()
    assert migration == migration_mirror


build_partner_report = ledger.build_partner_report
REPORT_SCHEMA_VERSION = ledger.REPORT_SCHEMA_VERSION


def test_partner_report_is_deterministic_regardless_of_order_and_timestamps():
    first = _record(provider_request_id="request-a")
    second = _record(
        normalized_question='{"code":"sqrt(9)"}',
        normalized_input_sha256="e" * 64,
        provider_request_id="request-b",
        verdict="SUPPORTED",
    )
    report_a = build_partner_report([first, second])
    report_b = build_partner_report([
        dict(second, createdAt="2099-01-01T00:00:00Z"),
        dict(first, createdAt="1999-01-01T00:00:00Z"),
    ])
    assert report_a["reportSha256"] == report_b["reportSha256"]
    assert report_a["schemaVersion"] == REPORT_SCHEMA_VERSION
    assert report_a["recordCount"] == 2
    assert report_a["verdictCounts"]["SUPPORTED"] == 1
    assert report_a["verdictCounts"]["INCONCLUSIVE"] == 1
    assert report_a["components"] == ["WolframLanguageComputation"]


def test_partner_report_never_carries_credential_fingerprints_or_created_at():
    report = build_partner_report([_record()])
    rendered = repr(report)
    assert "credentialFingerprint" not in rendered
    assert "createdAt" not in rendered
    assert "d" * 64 not in rendered


def test_partner_report_rejects_private_documentation_class():
    private = _record(documentation_class="PRIVATE_PROVIDER_EVIDENCE")
    with pytest.raises(PartnerAnalysisError, match="rejects private or unknown documentation classes"):
        build_partner_report([private])


def test_partner_report_rejects_tampered_record():
    tampered = _record()
    tampered["derivedConclusion"] = "Rewritten conclusion without hash change."
    with pytest.raises(PartnerAnalysisError, match="refusing tampered input"):
        build_partner_report([tampered])


def test_partner_report_rejects_secret_shaped_material():
    tampered = _record()
    tampered["derivedConclusion"] = "Authorization: forged-header-value"
    with pytest.raises(PartnerAnalysisError, match="secret-shaped"):
        build_partner_report([tampered])


def test_partner_report_rejects_non_sequence_input():
    with pytest.raises(PartnerAnalysisError, match="sequence of analysis records"):
        build_partner_report("not-records")
    with pytest.raises(PartnerAnalysisError, match="sequence of analysis records"):
        build_partner_report({"record": "not-a-sequence"})


def test_partner_report_surfaces_unresolved_questions_honestly():
    decided = _record(
        normalized_question='{"code":"2+2"}',
        normalized_input_sha256="f" * 64,
        verdict="SUPPORTED",
    )
    blocked = _record(
        verdict="UNAVAILABLE",
        provider_response_sha256=None,
        derived_conclusion="Credential provisioning pending; no canary executed.",
    )
    report = build_partner_report([decided, blocked])
    assert report["verdictCounts"]["UNAVAILABLE"] == 1
    assert [item["verdict"] for item in report["unresolvedQuestions"]] == ["UNAVAILABLE"]
    assert report["unresolvedQuestions"][0]["analysisRecordSha256"] == blocked["analysisRecordSha256"]


def test_partner_report_includes_hf_publication_only_for_verified_class():
    published = _record(
        documentation_class="HF_PUBLISHED_VERIFIED",
        hf_publication_ref="Thorsu/sovereign-evidence-observatory:batch-1",
        hf_target_revision="target-revision-1",
    )
    report = build_partner_report([_record(), published])
    by_sha = {entry["analysisRecordSha256"]: entry for entry in report["records"]}
    assert by_sha[_record()["analysisRecordSha256"]]["hfPublication"] is None
    hf_entry = by_sha[published["analysisRecordSha256"]]["hfPublication"]
    assert hf_entry == {
        "hfPublicationRef": "Thorsu/sovereign-evidence-observatory:batch-1",
        "hfTargetRevision": "target-revision-1",
    }
