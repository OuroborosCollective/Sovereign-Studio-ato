from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_SOURCE = BACKEND / "app.py"


def _route_source() -> str:
    source = APP_SOURCE.read_text(encoding="utf-8")
    start = source.index('@app.route("/api/toolchain/github/open-pr-review"')
    end = source.index('@app.route("/api/toolchain/preview-patch"', start)
    return source[start:end]


def test_open_pr_review_is_syntax_valid_and_read_only() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    ast.parse(source)
    route = _route_source()

    assert '@require_session' in route
    assert '_tc_allowed(owner, repo)' in route
    assert '_tc_gh_get(' in route
    assert '_tc_gh_post(' not in route
    assert '_tc_gh_put(' not in route
    assert 'state=open&per_page=' in route
    assert '/check-runs?per_page=100' in route
    assert '/files?per_page=100' in route
    assert '"reviewMode": "read_only"' in route
    assert '"githubWriteRequired": False' in route
    assert '"executorStarted": False' in route
    assert '"bounded": True' in route


def test_open_pr_review_exposes_merge_check_and_generated_artifact_evidence() -> None:
    route = _route_source()

    assert '"mergeable": mergeable' in route
    assert '"mergeableState": mergeable_state' in route
    assert '"changedFiles": int(detail.get("changed_files")' in route
    assert '"generatedArtifactCandidates": generated_candidates[:20]' in route
    assert '"successful": len(successful_checks)' in route
    assert '"pending": len(pending_checks)' in route
    assert '"failed": len(failed_checks)' in route
    assert 'blockers.append("merge_conflict")' in route
    assert 'blockers.append("failed_checks")' in route
    assert 'blockers.append("pending_checks")' in route


def test_generated_artifact_detection_stays_candidate_only() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    helper_start = source.index('_PR_GENERATED_PATH_MARKERS =')
    helper_end = source.index('@app.route("/api/toolchain/github/open-pr-review"', helper_start)
    helper = source[helper_start:helper_end]

    assert '"/generated/"' in helper
    assert '"/dist/"' in helper
    assert '"/build/"' in helper
    assert 'normalized.endswith(".min.js")' in helper
    assert 'package-lock.json' not in helper
