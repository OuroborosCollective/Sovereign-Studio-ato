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
assert_partner_safe = ledger.assert_partner_safe
attach_hf_publication = ledger.attach_hf_publication
build_partner_analysis_record = ledger.build_partner_analysis_record
build_partner_handoff_pack = ledger.build_partner_handoff_pack
evidence_passport_reference = ledger.evidence_passport_reference
load_partner_analyses = ledger.load_partner_analyses
persist_partner_analysis = ledger.persist_partner_analysis
public_partner_projection = ledger.public_partner_projection
render_partner_handoff_markdown = ledger.render_partner_handoff_markdown
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

    for name in (
        "058_wolfram_cag_partner_analysis.sql",
        "059_wolfram_cag_partner_analysis_observations.sql",
    ):
        migration = (ROOT / "backend" / "migrations" / name).read_bytes()
        migration_mirror = (ROOT / "scripts" / "sovereign-backend" / "migrations" / name).read_bytes()
        assert migration == migration_mirror


def test_same_evidence_same_hash_regardless_of_metadata_and_list_order():
    first = _record(created_at="2026-08-21T20:00:00Z", limitations=["b limit", "a limit"])
    second = _record(created_at="2026-08-22T20:00:00Z", limitations=["a limit", "b limit", "a limit"])
    assert first["analysisRecordSha256"] == second["analysisRecordSha256"]
    assert first["limitations"] == ["a limit", "b limit"]


def test_redaction_regression_corpus_is_hard_rejected_at_build_time():
    corpus = [
        "Authorization: Bearer abcdefgh12345678",
        "Bearer abcdefgh12345678",
        "api_key: abcd1234",
        "token=abcdefgh",
        "secret: hunter2secret",
        "password = correct-horse-battery",
        "ghp_" + "a" * 24,
        "-----BEGIN PRIVATE KEY-----",
        "contact: someone@example.com",
        "raw chain-of-thought transcript",
        "<|im_start|>system prompt leak",
    ]
    for payload in corpus:
        with pytest.raises(PartnerAnalysisError, match="secret-shaped"):
            _record(derived_conclusion=payload)


def test_redaction_gate_rejects_secret_keys_and_values_in_projections():
    with pytest.raises(PartnerAnalysisError, match="forbidden key marker"):
        assert_partner_safe({"nested": {"api_key": "redacted-shape"}})
    with pytest.raises(PartnerAnalysisError, match="secret-shaped"):
        assert_partner_safe({"entries": ["fine", "someone@example.com"]})
    with pytest.raises(PartnerAnalysisError, match="secret-shaped"):
        assert_partner_safe(["Authorization: Bearer abcdefgh12345678"])
    assert_partner_safe(public_partner_projection(_record()))


def test_quota_and_rate_limit_metadata_are_bounded_and_secret_checked():
    record = _record(
        quota_metadata={"quotaRemaining": "99"},
        rate_limit_metadata={"rateLimitRemaining": "9"},
    )
    assert record["quotaMetadata"] == {"quotaRemaining": "99"}
    assert record["rateLimitMetadata"] == {"rateLimitRemaining": "9"}
    with pytest.raises(PartnerAnalysisError, match="secret-shaped"):
        _record(quota_metadata={"quotaRemaining": "api_key: abcd1234"})
    with pytest.raises(PartnerAnalysisError, match="scalar"):
        _record(rate_limit_metadata={"nested": {"too": "deep"}})


def test_pack_is_deterministic_for_same_record_set():
    supported = _record(
        verdict="SUPPORTED",
        derived_conclusion="CAG result matches the claim within tolerance.",
        component="WolframAlphaResults",
    )
    contradicted = _record(
        verdict="CONTRADICTED",
        derived_conclusion="CAG result contradicts the claim.",
        component="WolframAlphaContext",
        limitations=["Contradiction retained honestly for partner review."],
    )
    first = build_partner_handoff_pack([supported, contradicted], generated_at="2026-08-22T00:00:00Z")
    second = build_partner_handoff_pack([contradicted, supported], generated_at="2026-08-23T00:00:00Z")
    assert first["packSha256"] == second["packSha256"]
    assert first["recordCount"] == 2
    assert first["summary"]["verdictCounts"] == {"CONTRADICTED": 1, "SUPPORTED": 1}
    assert first["generatedAt"] != second["generatedAt"]


def test_pack_keeps_source_contradiction_visible_and_public():
    supported = _record(verdict="SUPPORTED", derived_conclusion="CAG supports the claim.")
    contradicted = _record(
        verdict="CONTRADICTED",
        derived_conclusion="CAG contradicts the same claim.",
        component="WolframLanguageHints",
    )
    pack = build_partner_handoff_pack([supported, contradicted])
    verdicts = {entry["verdict"] for entry in pack["analyses"]}
    assert verdicts == {"SUPPORTED", "CONTRADICTED"}
    assert all("credentialFingerprintSha256" not in entry for entry in pack["analyses"])
    rendered = repr(pack)
    assert "credentialFingerprintSha256" not in rendered


def test_pack_quota_observations_only_when_actually_observed():
    observed = _record(quota_metadata={"quotaRemaining": "99"})
    unobserved = _record(component="WolframAlphaResults")
    pack = build_partner_handoff_pack([observed, unobserved])
    assert len(pack["quotaObservations"]) == 1
    assert pack["quotaObservations"][0]["quotaMetadata"] == {"quotaRemaining": "99"}


def test_pack_redaction_gate_blocks_smuggled_secret_material():
    record = _record()
    tampered = dict(record)
    tampered["derivedConclusion"] = "leaked someone@example.com"
    with pytest.raises(PartnerAnalysisError):
        build_partner_handoff_pack([tampered])


def test_attach_hf_publication_requires_target_readback_and_rebinds_identity():
    record = _record()
    with pytest.raises(PartnerAnalysisError, match="target readback"):
        attach_hf_publication(record, hf_publication_ref="Thorsu/sovereign-evidence-observatory:batch-1", hf_target_revision="")
    published = attach_hf_publication(
        record,
        hf_publication_ref="Thorsu/sovereign-evidence-observatory:batch-1",
        hf_target_revision="target-revision-1",
    )
    assert published["documentationClass"] == "HF_PUBLISHED_VERIFIED"
    assert published["analysisRecordSha256"] != record["analysisRecordSha256"]
    assert record["documentationClass"] == "PARTNER_REPORTABLE"


def test_evidence_passport_reference_is_hash_only():
    record = _record(evidence_passport_hash=None)
    reference = evidence_passport_reference(record)
    assert reference["analysisRecordSha256"] == record["analysisRecordSha256"]
    assert reference["schemaVersion"] == record["schemaVersion"]
    assert "derivedConclusion" not in reference
    assert "normalizedQuestion" not in reference
    assert "credentialFingerprintSha256" not in reference


def test_markdown_render_is_deterministic_and_secret_free():
    record = _record(quota_metadata={"quotaRemaining": "99"})
    pack = build_partner_handoff_pack([record], generated_at="2026-08-22T00:00:00Z")
    first = render_partner_handoff_markdown(pack)
    second = render_partner_handoff_markdown(pack)
    assert first == second
    assert "Wolfram CAG Partner Handoff Pack" in first
    assert pack["packSha256"] in first
    assert "credentialFingerprintSha256" not in first
    assert "never constitutes verification" in first or "never a verification" in first


def test_load_partner_analyses_maps_rows_and_orders_by_hash():
    class _LoadCursor:
        def __init__(self, rows):
            self.rows = rows
            self.closed = False

        def execute(self, sql):
            self.sql = sql

        def fetchall(self):
            return self.rows

        def close(self):
            self.closed = True

    class _LoadConnection:
        def __init__(self, rows):
            self.cursor_instance = _LoadCursor(rows)

        def cursor(self):
            return self.cursor_instance

    record = _record()
    row = (
        record["analysisId"], record["schemaVersion"], record["analysisRecordSha256"], REV, REV,
        None, None, record["cagComponent"], record["cagContractVersion"],
        record["normalizedQuestion"], record["normalizedInputSha256"], "request-1",
        "uuid-1", record["providerResponseSha256"], "d" * 64, record["verdict"],
        record["documentationClass"], record["derivedConclusion"], None,
        '{"quotaRemaining": "99"}', '{}',
        '["assumption"]', '["limitation"]', '["wolfram-official-cag-v1-contract"]',
        None, None, None, "2026-08-21 20:00:00+00",
    )
    connection = _LoadConnection([row])
    records = load_partner_analyses(connection)
    assert "ORDER BY record_sha256 ASC" in connection.cursor_instance.sql
    assert connection.cursor_instance.closed is True
    assert len(records) == 1
    loaded = records[0]
    assert loaded["analysisRecordSha256"] == record["analysisRecordSha256"]
    assert loaded["quotaMetadata"] == {"quotaRemaining": "99"}
    assert loaded["assumptions"] == ["assumption"]
    assert loaded["createdAt"] is not None
