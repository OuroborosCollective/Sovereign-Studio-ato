from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from evidence_observatory_cag_staging import (  # noqa: E402
    CAG_BENCHMARK_CASE_IDS,
    HF_CAG_REPO_ID,
    HF_CAG_STAGING_REVISION,
    build_cag_staging_rows,
    publish_cag_benchmark_staging,
)


def test_cag_staging_rows_are_exactly_the_twelve_public_fixture_cases():
    rows = build_cag_staging_rows()
    assert tuple(row["caseId"] for row in rows) == CAG_BENCHMARK_CASE_IDS
    assert len(rows) == 12
    assert len({row["caseSha256"] for row in rows}) == 12
    assert all(row["workflowState"] == "PUBLISHABLE" for row in rows)
    assert all(row["truthBoundary"]["liveCagResult"] is False for row in rows)
    assert rows[10]["verdict"] == "UNPROVEN"


def test_cag_staging_trigger_passes_no_rights_payload_and_uses_fixed_target():
    observed = {}

    def fake_publisher(**kwargs):
        observed.update(kwargs)
        return {"ok": True, "status": "DUPLICATE_NOOP"}

    result = publish_cag_benchmark_staging(publisher=fake_publisher)
    assert result["status"] == "DUPLICATE_NOOP"
    assert set(observed) == {"rows", "repo_id", "revision"}
    assert observed["repo_id"] == HF_CAG_REPO_ID
    assert observed["revision"] == HF_CAG_STAGING_REVISION
    assert tuple(row["caseId"] for row in observed["rows"]) == CAG_BENCHMARK_CASE_IDS


@pytest.mark.parametrize(
    ("repo_id", "revision", "error"),
    [
        ("other/repo", HF_CAG_STAGING_REVISION, "cag_benchmark_hf_target_mismatch"),
        (HF_CAG_REPO_ID, "main", "cag_benchmark_hf_revision_mismatch"),
    ],
)
def test_cag_staging_trigger_rejects_any_other_target_or_revision(repo_id, revision, error):
    with pytest.raises(RuntimeError, match=error):
        publish_cag_benchmark_staging(repo_id=repo_id, revision=revision, publisher=lambda **_: {})


def test_cag_admin_route_is_fixed_scope_and_never_marks_observatory_cases_published():
    source = (BACKEND / "evidence_observatory.py").read_text(encoding="utf-8")
    start = source.index('def observatory_publish_huggingface_cag_benchmark():')
    end = source.index('@app.route("/api/evidence-observatory/v1/arena/cases/', start)
    block = source[start:end]
    assert "publish_cag_benchmark_staging()" in block
    assert "CAG_BENCHMARK_CASE_IDS" in block
    assert "evidence_observatory_publish_receipts" in block
    assert "publication_status='PUBLISHED_VERIFIED'" in block
    assert "UPDATE evidence_observatory_cases" not in block
    assert "request.get_json" not in block
    assert "license_rights=" not in block
    assert "str(exc)" not in block
    assert '"error": "cag_benchmark_hf_publish_blocked"' in block
