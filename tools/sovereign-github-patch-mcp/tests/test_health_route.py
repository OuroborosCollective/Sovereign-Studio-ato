from fastapi.testclient import TestClient

import server


def test_health_route_precedes_catch_all_mcp_mount() -> None:
    response = TestClient(server.app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": "true", "service": "sovereign-github-patch-mcp"}
