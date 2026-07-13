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
MAX_TEXT = 1000


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
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json_body,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Owner-Freigabe-Backend ist nicht erreichbar: {exc}") from exc
        if response.status_code not in expected:
            raise RuntimeError(f"Owner-Freigabe-Backend meldet HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Owner-Freigabe-Backend lieferte keine gültige Antwort")
        return payload

    def create_openhands_request(
        self,
        *,
        title: str,
        reason: str,
        field_label: str = "OpenHands API-Key",
        expires_in_seconds: int = 900,
    ) -> dict[str, Any]:
        clean_title = str(title or "").strip()[:160]
        clean_reason = str(reason or "").strip()[:MAX_TEXT]
        clean_label = str(field_label or "").strip()[:120]
        if not clean_title or not clean_reason or not clean_label:
            raise ValueError("Titel, Begründung und Feldbezeichnung sind erforderlich")
        ttl = max(60, min(int(expires_in_seconds), 3600))
        payload = self._request(
            "POST",
            "/api/internal/owner-input/requests",
            json_body={
                "targetId": "openhands_api_key",
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
