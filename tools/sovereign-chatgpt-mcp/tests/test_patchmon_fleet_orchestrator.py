from __future__ import annotations

import server


def test_patchmon_workflow_green_reads_nested_pr_checks() -> None:
    payload = {
        "ok": True,
        "head_sha": "a" * 40,
        "checks": {
            "ok": True,
            "head_sha": "a" * 40,
            "checks": [
                {
                    "name": "Release Gate",
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "name": "Agent Runtime Tests",
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "name": "Assign reviewers",
                    "status": "completed",
                    "conclusion": "neutral",
                },
            ],
            "pending": [],
            "failed": [],
        },
    }

    assert server._patchmon_workflow_green(payload) is True


def test_patchmon_workflow_green_rejects_nested_pending_check() -> None:
    payload = {
        "checks": {
            "ok": False,
            "checks": [
                {
                    "name": "Release Gate",
                    "status": "in_progress",
                    "conclusion": None,
                },
                {
                    "name": "Agent Runtime Tests",
                    "status": "completed",
                    "conclusion": "success",
                },
            ],
            "pending": ["Release Gate"],
            "failed": [],
        },
    }

    assert server._patchmon_workflow_green(payload) is False


def test_patchmon_workflow_green_accepts_verified_workflow_run() -> None:
    payload = {
        "ok": True,
        "validation_complete": True,
        "passed": True,
        "status": "PASS",
        "run_status": "completed",
        "conclusion": "success",
        "jobs": [
            {
                "name": "Revision Guardian Orchestrator",
                "status": "completed",
                "conclusion": "success",
                "failed_steps": [],
            }
        ],
    }

    assert server._patchmon_workflow_green(payload) is True


def test_patchmon_workflow_green_rejects_incomplete_workflow_run() -> None:
    payload = {
        "validation_complete": False,
        "passed": False,
        "run_status": "in_progress",
        "conclusion": None,
        "jobs": [
            {
                "name": "Revision Guardian Orchestrator",
                "status": "in_progress",
                "conclusion": None,
            }
        ],
    }

    assert server._patchmon_workflow_green(payload) is False


def test_patchmon_workflow_green_keeps_flat_workflow_contract() -> None:
    payload = {
        "checks": [
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "skipped"},
        ]
    }

    assert server._patchmon_workflow_green(payload) is True


def test_patchmon_revision_binding_prefers_exact_main_workflow_after_merge() -> None:
    expected = "a" * 40
    pr_evidence = {"head_sha": "b" * 40}
    workflow_runs = [{"head_sha": expected}]

    observed, bound, source = server._patchmon_revision_binding(
        expected,
        pr_evidence,
        workflow_runs,
    )

    assert observed == expected
    assert bound is True
    assert source == "workflow_runs"


def test_patchmon_revision_binding_uses_squash_merge_commit_after_merge() -> None:
    expected = "a" * 40
    pr_evidence = {
        "state": "closed",
        "merged": True,
        "merged_at": "2026-08-24T03:00:15Z",
        "head_sha": "b" * 40,
        "merge_commit_sha": expected,
    }

    observed, bound, source = server._patchmon_revision_binding(
        expected,
        pr_evidence,
        [],
    )

    assert observed == expected
    assert bound is True
    assert source == "pull_request_merge_commit"


def test_patchmon_revision_binding_does_not_accept_old_pr_head_after_merge() -> None:
    merge_sha = "a" * 40
    head_sha = "b" * 40
    pr_evidence = {
        "state": "closed",
        "merged": True,
        "head_sha": head_sha,
        "merge_commit_sha": merge_sha,
    }

    observed, bound, source = server._patchmon_revision_binding(
        head_sha,
        pr_evidence,
        [],
    )

    assert observed == merge_sha
    assert bound is False
    assert source == "pull_request_merge_commit"


def test_patchmon_revision_binding_uses_open_pr_head_before_merge() -> None:
    expected = "a" * 40
    observed, bound, source = server._patchmon_revision_binding(
        expected,
        {"state": "open", "merged": False, "head_sha": expected},
        [],
    )

    assert observed == expected
    assert bound is True
    assert source == "pull_request_head"


def test_patchmon_revision_binding_fails_closed_when_merged_pr_has_no_merge_sha() -> None:
    observed, bound, source = server._patchmon_revision_binding(
        "a" * 40,
        {"state": "closed", "merged": True, "head_sha": "b" * 40},
        [],
    )

    assert observed == ""
    assert bound is False
    assert source == "pull_request_merge_commit"


def test_patchmon_revision_binding_fails_closed_when_one_run_has_no_revision() -> None:
    expected = "a" * 40
    workflow_runs = [{"head_sha": expected}, {"status": "PASS"}]

    observed, bound, source = server._patchmon_revision_binding(
        expected,
        {"head_sha": "b" * 40},
        workflow_runs,
    )

    assert observed == expected
    assert bound is False
    assert source == "workflow_runs"
