"""Fixed, fail-closed staging trigger for the public Wolfram CAG benchmark.

This module deliberately exposes no arbitrary case, repository, revision or rights
payload input.  The protected owner-managed rights receipt is loaded only inside
the existing Evidence Observatory publisher boundary.
"""
from __future__ import annotations

from typing import Any, Callable

from evidence_observatory_publisher import publish_huggingface_batch
from wolfram_cag_benchmark_publication import build_cag_benchmark_public_rows

HF_CAG_REPO_ID = "Thorsu/sovereign-evidence-observatory"
HF_CAG_STAGING_REVISION = "staging-atlas"
CAG_BENCHMARK_CASE_IDS = tuple(f"cag-bench-{index:03d}" for index in range(1, 13))


def build_cag_staging_rows() -> list[dict[str, Any]]:
    rows = build_cag_benchmark_public_rows()
    observed_ids = tuple(str(row.get("caseId") or "") for row in rows)
    if observed_ids != CAG_BENCHMARK_CASE_IDS:
        raise RuntimeError("cag_benchmark_public_case_scope_mismatch")
    if len({str(row.get("caseSha256") or "") for row in rows}) != len(rows):
        raise RuntimeError("cag_benchmark_public_case_hash_collision")
    if any((row.get("truthBoundary") or {}).get("liveCagResult") is not False for row in rows):
        raise RuntimeError("cag_benchmark_live_result_truth_boundary_violation")
    return rows


def publish_cag_benchmark_staging(
    *,
    repo_id: str = HF_CAG_REPO_ID,
    revision: str = HF_CAG_STAGING_REVISION,
    publisher: Callable[..., dict[str, Any]] = publish_huggingface_batch,
) -> dict[str, Any]:
    """Publish exactly the 12 public CAG fixtures through the secure publisher."""
    if str(repo_id or "").strip() != HF_CAG_REPO_ID:
        raise RuntimeError("cag_benchmark_hf_target_mismatch")
    if str(revision or "").strip() != HF_CAG_STAGING_REVISION:
        raise RuntimeError("cag_benchmark_hf_revision_mismatch")
    rows = build_cag_staging_rows()
    return publisher(rows=rows, repo_id=HF_CAG_REPO_ID, revision=HF_CAG_STAGING_REVISION)


__all__ = [
    "CAG_BENCHMARK_CASE_IDS",
    "HF_CAG_REPO_ID",
    "HF_CAG_STAGING_REVISION",
    "build_cag_staging_rows",
    "publish_cag_benchmark_staging",
]
