from __future__ import annotations

import json
import pytest
from flask import Flask
from test_agent_runtime_routes import FakeConnection, create_test_app, seed_job


@pytest.fixture
def test_client():
    conn = FakeConnection()
    app = create_test_app(conn)
    return conn, app.test_client()


def test_validation_endpoints_reject_non_dict_payloads(test_client):
    conn, client = test_client
    user_id = "user-1"
    headers = {"X-Test-User": user_id}
    invalid_payloads = [
        [1, 2, 3],
        "just string",
        12345,
        True,
    ]

    # Endpoints to test
    endpoints = [
        # 1. user_diagnose_sovereign_rescue
        ("/api/user/agent/rescue/diagnose", "POST"),
        # 2. user_diagnose_with_embedded_toolchain
        ("/api/user/agent/toolchain/diagnose", "POST"),
        # 3. user_preview_toolchain_migration_rollback
        ("/api/user/agent/toolchain/rollback-preview", "POST"),
        # 4. user_create_toolchain_agent_handoff
        ("/api/user/agent/toolchain/handoff", "POST"),
        # 5. user_validate_agent_mission
        ("/api/user/agent/validate-mission", "POST"),
        # 6. user_create_sovereign_agent_job
        ("/api/user/agent/jobs", "POST"),
        # 7. user_predict_agent_patterns
        ("/api/user/agent/patterns/predict", "POST"),
        # 8. user_search_reusable_memory
        ("/api/user/agent/memory/search", "POST"),
    ]

    for path, method in endpoints:
        for payload in invalid_payloads:
            response = client.post(
                path,
                headers=headers,
                json=payload,
            )
            assert response.status_code == 400, f"Expected 400 for {path} with payload {payload}"
            data = response.get_json()
            assert data == {"error": "A JSON object is required"}, f"Expected standard error format on {path}"


def test_job_specific_validation_endpoints_reject_non_dict_payloads(test_client):
    conn, client = test_client
    user_id = "user-1"
    job_id = "agent-1"
    seed_job(conn, user_id, job_id, status="running")
    headers = {"X-Test-User": user_id}
    invalid_payloads = [
        [1, 2, 3],
        "just string",
        12345,
        True,
    ]

    # Endpoints requiring job_id
    endpoints = [
        # 9. user_open_sovereign_agent_workspace_editor
        (f"/api/user/agent/jobs/{job_id}/editor/open", "POST"),
        # 10. user_generate_agent_job_changelog
        (f"/api/user/agent/jobs/{job_id}/changelog", "POST"),
        # 11. user_prepare_agent_draft_pr
        (f"/api/user/agent/jobs/{job_id}/draft-pr/prepare", "POST"),
        # 12. user_create_agent_draft_pr
        (f"/api/user/agent/jobs/{job_id}/draft-pr/create", "POST"),
        # 13. tool routes (via _run_tool_route)
        (f"/api/user/agent/jobs/{job_id}/tools/file", "POST"),
        (f"/api/user/agent/jobs/{job_id}/tools/git-status", "POST"),
        (f"/api/user/agent/jobs/{job_id}/tools/diff", "POST"),
        (f"/api/user/agent/jobs/{job_id}/tools/test", "POST"),
        (f"/api/user/agent/jobs/{job_id}/tools/janitor", "POST"),
    ]

    for path, method in endpoints:
        for payload in invalid_payloads:
            response = client.post(
                path,
                headers=headers,
                json=payload,
            )
            assert response.status_code == 400, f"Expected 400 for {path} with payload {payload}"
            data = response.get_json()
            assert data == {"error": "A JSON object is required"}, f"Expected standard error format on {path}"
