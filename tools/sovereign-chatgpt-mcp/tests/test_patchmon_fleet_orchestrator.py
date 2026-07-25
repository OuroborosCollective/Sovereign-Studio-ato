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


def test_patchmon_workflow_green_keeps_flat_workflow_contract() -> None:
    payload = {
        "checks": [
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "skipped"},
        ]
    }

    assert server._patchmon_workflow_green(payload) is True
