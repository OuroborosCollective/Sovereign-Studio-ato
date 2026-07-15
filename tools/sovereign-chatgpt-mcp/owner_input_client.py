"""Metadata-only client for owner-controlled protected input requests.

Protected values never pass through the MCP tool arguments or responses. The
owner enters them only in the authenticated backend owner surface.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

import requests

REQUEST_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")
MAX_TEXT = 1000
MAX_OPERATOR_MISSION = 20_000
MAX_OPERATOR_EVIDENCE = 250_000
OPERATOR_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
)
ALLOWED_TARGETS = {
    "openai_api_key": "OpenAI API-Key",
}


class OwnerInputClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.base_url = os.getenv(
            "SOVEREIGN_BACKEND_INTERNAL_URL",
            "http://sovereign-backend:8787",
        ).strip().rstrip("/")
        self.request_key = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        if not self.request_key:
            raise RuntimeError("SOVEREIGN_OWNER_REQUEST_KEY ist nicht konfiguriert")
        return {
            "X-Sovereign-Owner-Request-Key": self.request_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
        timeout: int = 15,
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json_body,
                timeout=max(1, min(int(timeout), 1200)),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Owner-Freigabe-Backend ist nicht erreichbar: {exc}") from exc
        if response.status_code not in expected:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {}
            detail = str(error_payload.get("blocker") or error_payload.get("error") or error_payload.get("reason") or "")[:240]
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Owner-Freigabe-Backend meldet HTTP {response.status_code}{suffix}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Owner-Freigabe-Backend lieferte keine gültige Antwort")
        return payload

    def create_request(
        self,
        *,
        target_id: str,
        title: str,
        reason: str,
        field_label: str = "",
        expires_in_seconds: int = 900,
    ) -> dict[str, Any]:
        selected_target = str(target_id or "").strip()
        if selected_target not in ALLOWED_TARGETS:
            raise ValueError("Owner-Ziel ist nicht allowlistet")
        clean_title = str(title or "").strip()[:160]
        clean_reason = str(reason or "").strip()[:MAX_TEXT]
        clean_label = str(field_label or ALLOWED_TARGETS[selected_target]).strip()[:120]
        if not clean_title or not clean_reason or not clean_label:
            raise ValueError("Titel, Begründung und Feldbezeichnung sind erforderlich")
        ttl = max(60, min(int(expires_in_seconds), 3600))
        payload = self._request(
            "POST",
            "/api/internal/owner-input/requests",
            json_body={
                "targetId": selected_target,
                "title": clean_title,
                "reason": clean_reason,
                "fieldLabel": clean_label,
                "expiresInSeconds": ttl,
            },
            expected=(201,),
        )
        request_payload = payload.get("request")
        if not isinstance(request_payload, dict) or not request_payload.get("id"):
            raise RuntimeError("Owner-Freigabe-Anfrage wurde nicht bestätigt")
        return {
            "ok": True,
            "status": "OWNER_INPUT_REQUESTED",
            "request": request_payload,
            "owner_url": "/owner-approvals",
            "protected_value_transport": "owner_ui_only",
            "llm_can_receive_protected_value": False,
        }

    def status(self, request_id: str) -> dict[str, Any]:
        selected = str(request_id or "").strip()
        if not REQUEST_ID_RE.fullmatch(selected):
            raise ValueError("request_id ist ungültig")
        try:
            uuid.UUID(selected)
        except ValueError as exc:
            raise ValueError("request_id ist ungültig") from exc
        payload = self._request(
            "GET",
            f"/api/internal/owner-input/requests/{selected}",
        )
        request_payload = payload.get("request")
        if not isinstance(request_payload, dict):
            raise RuntimeError("Owner-Freigabe-Status ist unvollständig")
        return {
            "ok": True,
            "status": "OWNER_INPUT_STATUS",
            "request": request_payload,
            "protected_value_returned": False,
        }


class ControllerRuntimeClient(OwnerInputClient):
    def _run_id(self, run_id: str) -> str:
        selected = str(run_id or "").strip()
        if not RUN_ID_RE.fullmatch(selected):
            raise ValueError("run_id ist ungültig")
        return selected

    def start_run(self, mission: str, evidence: str = "") -> dict[str, Any]:
        bounded_mission = str(mission or "").strip()
        bounded_evidence = str(evidence or "").strip()
        if not bounded_mission:
            raise ValueError("mission ist erforderlich")
        if len(bounded_mission) > MAX_OPERATOR_MISSION:
            raise ValueError("mission überschreitet das Operator-Limit")
        if len(bounded_evidence) > MAX_OPERATOR_EVIDENCE:
            raise ValueError("evidence überschreitet das Operator-Limit")
        normalized = f"{bounded_mission}\n{bounded_evidence}".casefold()
        if any(marker in normalized for marker in OPERATOR_SECRET_MARKERS):
            raise ValueError("Secret-förmiger Inhalt ist im Operator-Start verboten")
        return self._request(
            "POST",
            "/api/internal/controller/runs",
            json_body={"mission": bounded_mission, "evidence": bounded_evidence},
            expected=(200, 202, 502, 503),
            timeout=1200,
        )

    def list_runs(self, limit: int = 20) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 100))
        payload = self._request(
            "GET",
            f"/api/internal/controller/runs?limit={bounded_limit}",
            timeout=30,
        )
        return {
            **payload,
            "status": "CONTROLLER_RUNS",
            "protected_values_returned": False,
        }

    def run_status(self, run_id: str) -> dict[str, Any]:
        selected = self._run_id(run_id)
        payload = self._request(
            "GET",
            f"/api/internal/controller/runs/{selected}",
            timeout=30,
        )
        return {
            **payload,
            "status": "CONTROLLER_RUN_STATUS",
            "protected_values_returned": False,
        }

    def resume_run(self, run_id: str, evidence: str = "") -> dict[str, Any]:
        selected = self._run_id(run_id)
        bounded_evidence = str(evidence or "").strip()
        if len(bounded_evidence) > MAX_OPERATOR_EVIDENCE:
            raise ValueError("evidence überschreitet das Operator-Limit")
        normalized = bounded_evidence.casefold()
        if any(marker in normalized for marker in OPERATOR_SECRET_MARKERS):
            raise ValueError("Secret-förmige Evidence ist im Operator-Resume verboten")
        return self._request(
            "POST",
            f"/api/internal/controller/runs/{selected}/resume",
            json_body={"evidence": bounded_evidence},
            expected=(200, 202, 409, 502, 503),
            timeout=1200,
        )
