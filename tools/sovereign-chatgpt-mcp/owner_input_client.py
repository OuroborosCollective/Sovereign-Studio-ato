"""Metadata-only client for owner-controlled protected input requests.

Protected values never pass through the MCP tool arguments or responses. The
owner enters them only in the authenticated backend owner surface.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import uuid
from typing import Any

import requests

REQUEST_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")
EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
EXTERNAL_EVENT_SOURCES = frozenset({"mcp", "broker", "github", "browserless", "tika", "gotenberg", "database"})
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
    "openrouter_api_key": "OpenRouter API-Key",
    "litellm_provider_key": "LiteLLM Provider API-Key",
    "proven_learning_confirmation": "Exakter Learning-Plan-Hash",
}


class OwnerInputClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.base_url = os.getenv(
            "SOVEREIGN_BACKEND_INTERNAL_URL",
            "http://sovereign-backend:8787",
        ).strip().rstrip("/")
        self.request_key = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
        public_url = os.getenv(
            "SOVEREIGN_BACKEND_PUBLIC_URL",
            "https://sovereign-backend.arelorian.de",
        ).strip().rstrip("/")
        parsed_public_url = urllib.parse.urlsplit(public_url)
        if (
            parsed_public_url.scheme != "https"
            or not parsed_public_url.hostname
            or parsed_public_url.username
            or parsed_public_url.password
            or parsed_public_url.query
            or parsed_public_url.fragment
        ):
            raise RuntimeError("SOVEREIGN_BACKEND_PUBLIC_URL muss eine sichere HTTPS-Origin sein")
        self.public_base_url = public_url
        self.session = session or requests.Session()

    def _owner_url(self, request_id: str) -> str:
        selected = str(request_id or "").strip()
        if not REQUEST_ID_RE.fullmatch(selected):
            raise RuntimeError("Owner-Freigabe-Anfrage lieferte keine gültige Request-ID")
        try:
            normalized = str(uuid.UUID(selected))
        except ValueError as exc:
            raise RuntimeError("Owner-Freigabe-Anfrage lieferte keine gültige Request-ID") from exc
        return (
            f"{self.public_base_url}/owner-approvals"
            f"?request_id={urllib.parse.quote(normalized, safe='')}"
        )

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
        owner_url = self._owner_url(str(request_payload["id"]))
        return {
            "ok": True,
            "status": "OWNER_INPUT_REQUESTED",
            "request": request_payload,
            "owner_url": owner_url,
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
            "owner_url": self._owner_url(selected),
            "protected_value_returned": False,
        }

    def activate_provider_route(
        self,
        *,
        route_id: str,
        owner_request_id: str,
    ) -> dict[str, Any]:
        selected_route = str(route_id or "").strip()
        selected_request = str(owner_request_id or "").strip()
        if not ROUTE_ID_RE.fullmatch(selected_route):
            raise ValueError("route_id ist ungültig")
        if not REQUEST_ID_RE.fullmatch(selected_request):
            raise ValueError("owner_request_id ist ungültig")
        try:
            normalized_request = str(uuid.UUID(selected_request))
        except ValueError as exc:
            raise ValueError("owner_request_id ist ungültig") from exc
        payload = self._request(
            "POST",
            (
                "/api/internal/llm/provider-deployments/"
                f"{urllib.parse.quote(selected_route, safe='')}/activate"
            ),
            json_body={"ownerRequestId": normalized_request},
            expected=(200, 409, 500, 502),
            timeout=180,
        )
        return {
            **payload,
            "status": str(payload.get("status") or "PROVIDER_ACTIVATION_RESULT"),
            "routeId": str(payload.get("routeId") or selected_route),
            "ownerRequestId": normalized_request,
            "protected_values_returned": False,
            "activation_transport": "private_owner_service_bridge",
        }

    def activate_litellm_provider_route(self, route_id: str) -> dict[str, Any]:
        selected = str(route_id or "").strip()
        if not ROUTE_ID_RE.fullmatch(selected):
            raise ValueError("route_id ist ungültig")
        payload = self._request(
            "POST",
            f"/api/internal/llm/provider-deployments/{selected}/activate",
            expected=(200, 400, 409, 500, 502, 503),
            timeout=1200,
        )
        return {
            **payload,
            "routeId": str(payload.get("routeId") or selected),
            "protected_values_returned": False,
            "secret_argument_accepted": False,
        }

    def plan_proven_learning(self, record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise ValueError("record muss ein Objekt sein")
        return self._request(
            "POST",
            "/api/internal/proven-learning/plan",
            json_body={"record": record},
        )

    def apply_proven_learning(
        self,
        *,
        request_id: str = "",
        confirmation_sha256: str,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        selected_request = str(request_id or "").strip()
        selected_hash = str(confirmation_sha256 or "").strip().lower()
        if selected_request:
            if not REQUEST_ID_RE.fullmatch(selected_request):
                raise ValueError("request_id ist ungültig")
            try:
                uuid.UUID(selected_request)
            except ValueError as exc:
                raise ValueError("request_id ist ungültig") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", selected_hash):
            raise ValueError("confirmation_sha256 ist ungültig")
        if not isinstance(record, dict):
            raise ValueError("record muss ein Objekt sein")
        return self._request(
            "POST",
            "/api/internal/proven-learning/apply",
            json_body={
                "requestId": selected_request,
                "confirmationSha256": selected_hash,
                "record": record,
            },
            expected=(200,),
            timeout=120,
        )


class ProviderRuntimeClient(OwnerInputClient):
    """Secret-free operator client for paid routes and managed direct FreeLLM."""

    @staticmethod
    def _source_id(source_id: str) -> str:
        selected = str(source_id or "").strip()
        try:
            return str(uuid.UUID(selected))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("source_id ist ungültig") from exc

    @staticmethod
    def _route_id(route_id: str) -> str:
        selected = str(route_id or "").strip()
        if not ROUTE_ID_RE.fullmatch(selected):
            raise ValueError("route_id ist ungültig")
        return selected

    def list_deployments(self) -> dict[str, Any]:
        payload = self._request(
            "GET",
            "/api/internal/llm/provider-deployments",
            timeout=30,
        )
        deployments = payload.get("deployments")
        return {
            **payload,
            "deployments": deployments if isinstance(deployments, list) else [],
            "protected_values_returned": False,
        }

    def freellm_status(self) -> dict[str, Any]:
        payload = self._request(
            "GET",
            "/api/internal/llm/freellm/providers",
            timeout=30,
        )
        providers = payload.get("providers")
        return {
            **payload,
            "providers": providers if isinstance(providers, list) else [],
            "protected_values_returned": False,
        }

    def freellm_reconcile(self, source_id: str, max_models: int = 20) -> dict[str, Any]:
        selected = self._source_id(source_id)
        if isinstance(max_models, bool) or not isinstance(max_models, int):
            raise ValueError("max_models muss eine ganze Zahl sein")
        bounded_max = max(1, min(max_models, 50))
        payload = self._request(
            "POST",
            f"/api/internal/llm/freellm/providers/{selected}/reconcile",
            json_body={"maxModels": bounded_max},
            expected=(200, 409, 503),
            timeout=1200,
        )
        return {
            **payload,
            "sourceId": str(payload.get("sourceId") or selected),
            "protected_values_returned": False,
            "secret_argument_accepted": False,
        }

    def activate(self, route_id: str) -> dict[str, Any]:
        selected = self._route_id(route_id)
        deployments = self.list_deployments().get("deployments", [])
        matching = next(
            (
                item for item in deployments
                if isinstance(item, dict)
                and str(item.get("routeId") or item.get("route_id") or "").strip() == selected
            ),
            None,
        )
        if not isinstance(matching, dict):
            raise RuntimeError("Provider-Route wurde in den Deployment-Metadaten nicht gefunden")
        owner_request_id = str(
            matching.get("ownerRequestId")
            or matching.get("owner_request_id")
            or ""
        ).strip()
        if not owner_request_id:
            raise RuntimeError("Provider-Route besitzt keine gebundene Owner-Request-ID")
        return self.activate_provider_route(
            route_id=selected,
            owner_request_id=owner_request_id,
        )


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

    def record_external_event(
        self,
        run_id: str,
        *,
        source: str,
        external_identity: str,
        event_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        selected = self._run_id(run_id)
        normalized_source = str(source or "").strip().lower()
        normalized_identity = str(external_identity or "").strip()
        normalized_type = str(event_type or "").strip()[:120]
        normalized_summary = str(summary or "").strip()[:2000]
        if normalized_source not in EXTERNAL_EVENT_SOURCES:
            raise ValueError("source is not allowlisted for external events")
        if not EXTERNAL_ID_RE.fullmatch(normalized_identity):
            raise ValueError("external_identity is invalid")
        if not normalized_type or not normalized_summary:
            raise ValueError("event_type and summary are required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        body = {
            "source": normalized_source,
            "externalIdentity": normalized_identity,
            "eventType": normalized_type,
            "summary": normalized_summary,
            "payload": payload,
        }
        rendered = json.dumps(body, ensure_ascii=False, sort_keys=True)
        if len(rendered.encode("utf-8")) > 120_000:
            raise ValueError("external event exceeds the bounded input limit")
        if any(marker in rendered.casefold() for marker in OPERATOR_SECRET_MARKERS):
            raise ValueError("secret-shaped material is forbidden in external events")
        response = self._request(
            "POST",
            f"/api/internal/controller/runs/{selected}/events/external",
            json_body=body,
            expected=(200, 201),
            timeout=30,
        )
        return {
            **response,
            "status": "CONTROLLER_EXTERNAL_EVENT_RECORDED",
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
