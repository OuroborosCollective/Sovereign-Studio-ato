"""Bounded autonomous candidate scanner for Sovereign Free Revolver v3.

This module was adapted from the owner-supplied ``llm_route_scanner.py``.
It intentionally does not expose a second FastAPI application and never sends
user prompts to discovered endpoints. Unknown community proxies remain
untrusted candidates until a separate, evidence-backed onboarding path promotes
them. The production FreeLLM resolver continues to consume only PostgreSQL
routes that already passed its own pricing and runtime gates.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

import requests

from free_route_source_contracts import (
    STRUCTURED_SOURCE_SPECS,
    TEXT_SOURCE_SPECS,
    canonical_sha256,
    explicit_completion_endpoints,
    independent_source_consensus,
    parse_mnfst_free_quota_catalog,
    source_spec_by_fetch_url,
)


SOURCE_URLS: tuple[str, ...] = tuple(
    str(spec["fetchUrl"]) for spec in TEXT_SOURCE_SPECS
)
STRUCTURED_SOURCE_URLS: tuple[str, ...] = tuple(
    str(spec["fetchUrl"]) for spec in STRUCTURED_SOURCE_SPECS
)

SEED_ROUTES: tuple[str, ...] = (
    # Community proxy seeds (may require auth — kept for completeness)
    "https://api.airforce/v1/chat/completions",
    "https://free.churchless.tech/v1/chat/completions",
    "https://api.freetheai.xyz/v1/chat/completions",
    "https://qwen.aikit.club/v1/chat/completions",
    # Truly keyless public endpoints (no API key required)
    "https://deepseek-r1.endpoints.kepler.ai.cloud.ovh.net/api/openai_compat/v1/chat/completions",
    "https://llama-3-3-70b-instruct.endpoints.kepler.ai.cloud.ovh.net/api/openai_compat/v1/chat/completions",
    "https://text.pollinations.ai/openai",
    "https://mlvoca.com/v1/chat/completions",
    "https://qwen-qwen2-5-72b-instruct.hf.space/v1/chat/completions",
)

_DENIED_HOST_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".invalid",
)
_DENIED_PROVIDER_HOSTS = {
    "api.openai.com",
    "openai.com",
    "api.anthropic.com",
    "anthropic.com",
    "openrouter.ai",
    "api.openrouter.ai",
}
_MAX_SOURCE_BYTES = 1_000_000
_MAX_CANARY_BYTES = 262_144
_DEFAULT_SCAN_INTERVAL_SECONDS = 3_600
_DEFAULT_INITIAL_DELAY_SECONDS = 30
_DEFAULT_MAX_CANDIDATES = 24
_DEFAULT_MAX_WORKERS = 4
_DEFAULT_LEASE_SECONDS = 900
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXTRACTION_POLICY = "explicit-completion-endpoint-only"


def _runtime_identity() -> dict[str, Any]:
    source_revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    image_digest = os.getenv("SOVEREIGN_IMAGE_DIGEST", "").strip().lower()
    return {
        "sourceRevision": source_revision if _SOURCE_REVISION_RE.fullmatch(source_revision) else "unverified",
        "sourceRevisionVerified": bool(_SOURCE_REVISION_RE.fullmatch(source_revision)),
        "imageDigest": image_digest if _IMAGE_DIGEST_RE.fullmatch(image_digest) else "unverified",
        "imageDigestVerified": bool(_IMAGE_DIGEST_RE.fullmatch(image_digest)),
    }


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    route_url: str
    source_urls: tuple[str, ...]
    status: str
    confirmation_count: int
    http_status: int | None
    failure_family: str
    latency_ms: int
    response_sha256: str
    free_quota_evidence: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ScanSnapshot:
    run_id: str
    status: str
    started_epoch: int
    completed_epoch: int
    source_count: int
    source_error_count: int
    candidate_count: int
    canary_passed_count: int
    blocked_count: int
    rejected_count: int
    source_errors: tuple[str, ...]
    candidates: tuple[CandidateEvidence, ...]
    failure_family: str = ""

    def safe_payload(self) -> dict[str, Any]:
        payload = {
            "runId": self.run_id,
            "status": self.status,
            "startedEpoch": self.started_epoch,
            "completedEpoch": self.completed_epoch,
            "sourceCount": self.source_count,
            "sourceErrorCount": self.source_error_count,
            "candidateCount": self.candidate_count,
            "canaryPassedCount": self.canary_passed_count,
            "blockedCount": self.blocked_count,
            "rejectedCount": self.rejected_count,
            "sourceErrors": list(self.source_errors),
            "failureFamily": self.failure_family or None,
            "extractionPolicy": _EXTRACTION_POLICY,
            "sentenceDerivedEndpointsAccepted": False,
            "independentSourceConsensusRequiredForOnboarding": True,
            "runtimeIdentity": _runtime_identity(),
            "sourceFetchTransport": "direct-https-bounded",
            "scrapestackDependency": False,
            "structuredFetchErrors": True,
            "rawProviderResponsesPersisted": False,
            "userPromptsForwarded": False,
            "automaticRouteActivation": False,
        }
        payload["evidenceSha256"] = canonical_sha256(payload)
        return payload


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _read_limited_response(response: Any, limit: int) -> bytes:
    declared = int(response.headers.get("Content-Length") or 0)
    if declared > limit:
        raise ValueError("response_too_large")
    chunks: list[bytes] = []
    size = 0
    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        for chunk in iterator(chunk_size=16_384):
            if not chunk:
                continue
            size += len(chunk)
            if size > limit:
                raise ValueError("response_too_large")
            chunks.append(bytes(chunk))
        return b"".join(chunks)
    payload = bytes(getattr(response, "content", b"") or b"")
    if len(payload) > limit:
        raise ValueError("response_too_large")
    return payload


def _normalize_candidate_endpoint(value: str) -> str:
    candidate = str(value or "").strip().rstrip(".,;)]}\"")
    try:
        parsed = urllib.parse.urlsplit(candidate)
    except ValueError as exc:
        raise ValueError("candidate_url_invalid") from exc
    if parsed.scheme.lower() != "https":
        raise ValueError("candidate_https_required")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("candidate_host_invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("candidate_port_invalid") from exc
    if port not in {None, 443}:
        raise ValueError("candidate_nonstandard_port_blocked")
    host = parsed.hostname.rstrip(".").lower()
    if (
        host in _DENIED_PROVIDER_HOSTS
        or host == "localhost"
        or any(host.endswith(suffix) for suffix in _DENIED_HOST_SUFFIXES)
    ):
        raise ValueError("candidate_host_blocked")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("candidate_ip_literal_blocked")
    normalized_path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if normalized_path.rstrip("/") != "/v1/chat/completions" and not normalized_path.endswith(
        "/v1/chat/completions"
    ):
        raise ValueError("candidate_completion_path_required")
    return urllib.parse.urlunsplit(("https", host, normalized_path.rstrip("/"), "", ""))


def _resolve_public_addresses(host: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("candidate_dns_unavailable") from exc
    addresses = sorted({str(record[4][0]).split("%", 1)[0] for record in records})
    if not addresses:
        raise ValueError("candidate_dns_unavailable")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("candidate_dns_invalid") from exc
        if not parsed.is_global:
            raise ValueError("candidate_private_network_blocked")
    return tuple(addresses)


def _canary_content_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = str(message.get("content") or "").strip().casefold()
    content = re.sub(r"[^a-z]+", "", content)[:16]
    return content.startswith("ping") or content.startswith("ok")


class RouteManager:
    """Discover and canary untrusted route candidates without activating them."""

    def __init__(
        self,
        *,
        acquire_lease: Callable[[str, int], bool],
        release_lease: Callable[[str], None],
        persist_snapshot: Callable[[ScanSnapshot], None],
        session_factory: Callable[[], requests.Session] = requests.Session,
        source_urls: Iterable[str] = SOURCE_URLS,
        structured_source_urls: Iterable[str] = STRUCTURED_SOURCE_URLS,
        seed_routes: Iterable[str] = SEED_ROUTES,
    ) -> None:
        self.source_urls = tuple(source_urls)
        self.structured_source_urls = tuple(structured_source_urls)
        self.seed_routes = tuple(seed_routes)
        self._free_quota_evidence_by_route: dict[str, tuple[dict[str, Any], ...]] = {}
        self._acquire_lease = acquire_lease
        self._release_lease = release_lease
        self._persist_snapshot = persist_snapshot
        self._session_factory = session_factory
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._is_scanning = False

    @staticmethod
    def extract_endpoints_from_text(text: str) -> list[str]:
        """Accept only completion endpoints literally present in source text."""
        return explicit_completion_endpoints(text)

    def _source_session(self) -> requests.Session:
        session = self._session_factory()
        if hasattr(session, "trust_env"):
            session.trust_env = False
        return session

    def fetch_routes_from_sources(self) -> tuple[dict[str, set[str]], list[str], int]:
        routes: dict[str, set[str]] = {}
        quota_evidence: dict[str, list[dict[str, Any]]] = {}
        rejected = 0
        for route in self.seed_routes:
            try:
                normalized = _normalize_candidate_endpoint(route)
            except ValueError:
                rejected += 1
                continue
            routes.setdefault(normalized, set()).add("seed")

        source_errors: list[str] = []
        for source_url in self.source_urls:
            session = self._source_session()
            response = None
            try:
                response = session.get(
                    source_url,
                    headers={
                        "Accept": "text/plain,text/markdown;q=0.9",
                        "User-Agent": "sovereign-free-route-scanner/2",
                    },
                    timeout=15,
                    allow_redirects=False,
                    stream=True,
                )
                status = int(response.status_code)
                if status != 200:
                    source_errors.append(f"source_http_{status}")
                    continue
                raw = _read_limited_response(response, _MAX_SOURCE_BYTES)
                text = raw.decode("utf-8", errors="replace")
                spec = source_spec_by_fetch_url(source_url) or {}
                source_identity = str(spec.get("canonicalUrl") or source_url)
                for endpoint in self.extract_endpoints_from_text(text):
                    try:
                        normalized = _normalize_candidate_endpoint(endpoint)
                    except ValueError:
                        rejected += 1
                        continue
                    routes.setdefault(normalized, set()).add(source_identity)
            except requests.Timeout:
                source_errors.append("source_transport_timeout")
            except requests.RequestException:
                source_errors.append("source_transport_request_failed")
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                source_errors.append(f"source_{type(exc).__name__.lower()}"[:80])
            finally:
                close_response = getattr(response, "close", None)
                if callable(close_response):
                    close_response()
                close_session = getattr(session, "close", None)
                if callable(close_session):
                    close_session()

        for source_url in self.structured_source_urls:
            session = self._source_session()
            response = None
            try:
                response = session.get(
                    source_url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "sovereign-free-route-scanner/2",
                    },
                    timeout=15,
                    allow_redirects=False,
                    stream=True,
                )
                status = int(response.status_code)
                if status != 200:
                    source_errors.append(f"structured_source_http_{status}")
                    continue
                raw = _read_limited_response(response, _MAX_SOURCE_BYTES)
                payload = json.loads(raw.decode("utf-8"))
                spec = source_spec_by_fetch_url(source_url) or {}
                source_identity = str(spec.get("canonicalUrl") or source_url)
                parsed, source_rejected = parse_mnfst_free_quota_catalog(
                    payload,
                    source_url=source_identity,
                )
                rejected += source_rejected
                for item in parsed:
                    try:
                        normalized = _normalize_candidate_endpoint(str(item["endpoint"]))
                    except ValueError:
                        rejected += 1
                        continue
                    routes.setdefault(normalized, set()).add(source_identity)
                    quota_evidence.setdefault(normalized, []).append(dict(item["evidence"]))
            except requests.Timeout:
                source_errors.append("structured_source_transport_timeout")
            except requests.RequestException:
                source_errors.append("structured_source_transport_request_failed")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                source_errors.append(f"structured_source_{type(exc).__name__.lower()}"[:80])
            finally:
                close_response = getattr(response, "close", None)
                if callable(close_response):
                    close_response()
                close_session = getattr(session, "close", None)
                if callable(close_session):
                    close_session()

        self._free_quota_evidence_by_route = {
            route: tuple(items[:16]) for route, items in quota_evidence.items()
        }
        return routes, source_errors[:32], rejected

    def validate_route(self, route_url: str, source_urls: Iterable[str]) -> CandidateEvidence:
        started = time.monotonic()
        response_hash = ""
        last_status: int | None = None
        try:
            normalized = _normalize_candidate_endpoint(route_url)
            free_quota_evidence = self._free_quota_evidence_by_route.get(normalized, ())
            host = urllib.parse.urlsplit(normalized).hostname or ""
            _resolve_public_addresses(host)
            confirmations = 0
            for _confirmation in (1, 2):
                session = self._source_session()
                response = None
                try:
                    response = session.post(
                        normalized,
                        json={
                            "model": "gpt-3.5-turbo",
                            "messages": [
                                {"role": "user", "content": "Reply only with Ping."}
                            ],
                            "max_tokens": 5,
                            "temperature": 0,
                            "stream": False,
                        },
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "User-Agent": "sovereign-free-route-scanner/1",
                            "Authorization": "Bearer dummy-free-route-canary",
                        },
                        timeout=8,
                        allow_redirects=False,
                        stream=True,
                    )
                    last_status = int(response.status_code)
                    if last_status != 200:
                        family = (
                            "candidate_auth_required"
                            if last_status in {401, 403}
                            else "candidate_rate_limited"
                            if last_status == 429
                            else "candidate_upstream_5xx"
                            if last_status >= 500
                            else "candidate_http_rejected"
                        )
                        return CandidateEvidence(
                            normalized,
                            tuple(sorted(set(source_urls))),
                            "blocked",
                            confirmations,
                            last_status,
                            family,
                            int((time.monotonic() - started) * 1000),
                            response_hash,
                            free_quota_evidence,
                        )
                    raw = _read_limited_response(response, _MAX_CANARY_BYTES)
                    response_hash = hashlib.sha256(raw).hexdigest()
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        return CandidateEvidence(
                            normalized,
                            tuple(sorted(set(source_urls))),
                            "blocked",
                            confirmations,
                            last_status,
                            "candidate_response_invalid_json",
                            int((time.monotonic() - started) * 1000),
                            response_hash,
                            free_quota_evidence,
                        )
                    if not _canary_content_valid(payload):
                        return CandidateEvidence(
                            normalized,
                            tuple(sorted(set(source_urls))),
                            "blocked",
                            confirmations,
                            last_status,
                            "candidate_response_contract_failed",
                            int((time.monotonic() - started) * 1000),
                            response_hash,
                            free_quota_evidence,
                        )
                    confirmations += 1
                finally:
                    close_response = getattr(response, "close", None)
                    if callable(close_response):
                        close_response()
                    close_session = getattr(session, "close", None)
                    if callable(close_session):
                        close_session()
            return CandidateEvidence(
                normalized,
                tuple(sorted(set(source_urls))),
                "canary_passed",
                confirmations,
                last_status,
                "",
                int((time.monotonic() - started) * 1000),
                response_hash,
                free_quota_evidence,
            )
        except requests.Timeout:
            family = "candidate_timeout"
        except requests.RequestException:
            family = "candidate_transport_failed"
        except ValueError as exc:
            family = str(exc)[:120] or "candidate_validation_failed"
        except (OSError, TypeError):
            family = "candidate_validation_failed"
        return CandidateEvidence(
            str(route_url or "")[:500],
            tuple(sorted(set(source_urls))),
            "blocked",
            0,
            last_status,
            family,
            int((time.monotonic() - started) * 1000),
            response_hash,
            self._free_quota_evidence_by_route.get(str(route_url or ""), ()),
        )

    def scan_once(self) -> ScanSnapshot:
        run_id = str(uuid.uuid4())
        started = int(time.time())
        lease_seconds = _bounded_env_int(
            "SOVEREIGN_LLM_ROUTE_SCANNER_LEASE_SECONDS",
            _DEFAULT_LEASE_SECONDS,
            60,
            3_600,
        )
        if not self._acquire_lease(run_id, lease_seconds):
            return ScanSnapshot(
                run_id,
                "lease_held",
                started,
                int(time.time()),
                len(self.source_urls) + len(self.structured_source_urls),
                0,
                0,
                0,
                0,
                0,
                (),
                (),
                "scanner_lease_held",
            )
        with self._state_lock:
            self._is_scanning = True
        try:
            route_sources, source_errors, rejected = self.fetch_routes_from_sources()
            max_candidates = _bounded_env_int(
                "SOVEREIGN_LLM_ROUTE_SCANNER_MAX_CANDIDATES",
                _DEFAULT_MAX_CANDIDATES,
                1,
                100,
            )
            selected = sorted(route_sources)[:max_candidates]
            max_workers = min(
                len(selected) or 1,
                _bounded_env_int(
                    "SOVEREIGN_LLM_ROUTE_SCANNER_MAX_WORKERS",
                    _DEFAULT_MAX_WORKERS,
                    1,
                    8,
                ),
            )
            results: list[CandidateEvidence] = []
            with ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="llm-route-scanner",
            ) as executor:
                futures = {
                    executor.submit(
                        self.validate_route,
                        route,
                        route_sources[route],
                    ): route
                    for route in selected
                }
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception:
                        results.append(CandidateEvidence(
                            futures[future],
                            tuple(sorted(route_sources[futures[future]])),
                            "blocked",
                            0,
                            None,
                            "candidate_worker_failed",
                            0,
                            "",
                        ))
            results.sort(key=lambda item: item.route_url)
            snapshot = ScanSnapshot(
                run_id,
                "completed",
                started,
                int(time.time()),
                len(self.source_urls) + len(self.structured_source_urls),
                len(source_errors),
                len(results),
                sum(item.status == "canary_passed" for item in results),
                sum(item.status == "blocked" for item in results),
                rejected + max(0, len(route_sources) - len(selected)),
                tuple(source_errors),
                tuple(results),
            )
            self._persist_snapshot(snapshot)
            return snapshot
        except Exception as exc:
            snapshot = ScanSnapshot(
                run_id,
                "failed",
                started,
                int(time.time()),
                len(self.source_urls) + len(self.structured_source_urls),
                0,
                0,
                0,
                0,
                0,
                (),
                (),
                f"scanner_{type(exc).__name__.lower()}"[:120],
            )
            try:
                self._persist_snapshot(snapshot)
            except Exception:
                pass
            return snapshot
        finally:
            with self._state_lock:
                self._is_scanning = False
            self._release_lease(run_id)

    def _scan_loop(self) -> None:
        initial_delay = _bounded_env_int(
            "SOVEREIGN_LLM_ROUTE_SCANNER_INITIAL_DELAY_SECONDS",
            _DEFAULT_INITIAL_DELAY_SECONDS,
            0,
            600,
        )
        interval = _bounded_env_int(
            "SOVEREIGN_LLM_ROUTE_SCANNER_INTERVAL_SECONDS",
            _DEFAULT_SCAN_INTERVAL_SECONDS,
            300,
            86_400,
        )
        self._wake.wait(initial_delay)
        self._wake.clear()
        while not self._stop.is_set():
            self.scan_once()
            self._wake.wait(interval)
            self._wake.clear()

    def start(self) -> bool:
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return False
            self._thread = threading.Thread(
                target=self._scan_loop,
                daemon=True,
                name="sovereign-llm-route-scanner",
            )
            self._thread.start()
            return True

    def request_scan(self) -> None:
        self._wake.set()

    @property
    def is_scanning(self) -> bool:
        with self._state_lock:
            return self._is_scanning


def register_llm_route_scanner(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    audit: Callable[..., Any],
) -> RouteManager:
    """Register admin status/trigger routes and the production-only scan loop."""
    from flask import jsonify

    def acquire_lease(run_id: str, lease_seconds: int) -> bool:
        query(
            """INSERT INTO llm_route_scanner_runtime (singleton_id)
               VALUES (1) ON CONFLICT (singleton_id) DO NOTHING""",
            write=True,
        )
        row = query(
            """UPDATE llm_route_scanner_runtime
               SET lease_owner=%s::uuid,
                   lease_expires_at=NOW() + (%s * INTERVAL '1 second'),
                   last_started_at=NOW(), updated_at=NOW()
               WHERE singleton_id=1
                 AND (lease_expires_at IS NULL OR lease_expires_at < NOW())
               RETURNING lease_owner::text""",
            (run_id, lease_seconds),
            one=True,
            write=True,
        )
        return bool(row and str(row.get("lease_owner") or "") == run_id)

    def release_lease(run_id: str) -> None:
        try:
            query(
                """UPDATE llm_route_scanner_runtime
                   SET lease_owner=NULL, lease_expires_at=NULL,
                       last_completed_at=NOW(), updated_at=NOW()
                   WHERE singleton_id=1 AND lease_owner=%s::uuid""",
                (run_id,),
                write=True,
            )
        except Exception:
            pass

    def persist_snapshot(snapshot: ScanSnapshot) -> None:
        payload = snapshot.safe_payload()
        query(
            """INSERT INTO llm_route_scanner_runs
                   (id, status, source_count, source_error_count,
                    candidate_count, canary_passed_count, blocked_count,
                    rejected_count, failure_family, evidence,
                    started_at, completed_at)
               VALUES (
                   %s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,
                   to_timestamp(%s),to_timestamp(%s)
               )""",
            (
                snapshot.run_id,
                snapshot.status,
                snapshot.source_count,
                snapshot.source_error_count,
                snapshot.candidate_count,
                snapshot.canary_passed_count,
                snapshot.blocked_count,
                snapshot.rejected_count,
                snapshot.failure_family or None,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                snapshot.started_epoch,
                snapshot.completed_epoch,
            ),
            write=True,
        )
        for candidate in snapshot.candidates:
            query(
                """INSERT INTO llm_route_scanner_candidates
                       (route_url, route_sha256, host, source_urls, status,
                        canary_confirmation_count, last_http_status,
                        last_failure_family, last_latency_ms,
                        last_response_sha256, free_quota_evidence,
                        source_consensus, routing_eligible,
                        first_seen_at, last_seen_at, last_checked_at, updated_at)
                   VALUES (
                       %s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,false,
                       NOW(),NOW(),NOW(),NOW()
                   )
                   ON CONFLICT (route_url) DO UPDATE SET
                       route_sha256=EXCLUDED.route_sha256,
                       host=EXCLUDED.host,
                       source_urls=EXCLUDED.source_urls,
                       status=EXCLUDED.status,
                       canary_confirmation_count=EXCLUDED.canary_confirmation_count,
                       last_http_status=EXCLUDED.last_http_status,
                       last_failure_family=EXCLUDED.last_failure_family,
                       last_latency_ms=EXCLUDED.last_latency_ms,
                       last_response_sha256=EXCLUDED.last_response_sha256,
                       free_quota_evidence=EXCLUDED.free_quota_evidence,
                       source_consensus=EXCLUDED.source_consensus,
                       routing_eligible=false,
                       last_seen_at=NOW(), last_checked_at=NOW(), updated_at=NOW()""",
                (
                    candidate.route_url,
                    hashlib.sha256(candidate.route_url.encode("utf-8")).hexdigest(),
                    urllib.parse.urlsplit(candidate.route_url).hostname or "",
                    json.dumps(list(candidate.source_urls), ensure_ascii=False),
                    candidate.status,
                    candidate.confirmation_count,
                    candidate.http_status,
                    candidate.failure_family or None,
                    candidate.latency_ms,
                    candidate.response_sha256 or None,
                    json.dumps(list(candidate.free_quota_evidence), ensure_ascii=False),
                    independent_source_consensus(candidate.source_urls),
                ),
                write=True,
            )
            if (
                candidate.status == "canary_passed"
                and candidate.confirmation_count == 2
                and independent_source_consensus(candidate.source_urls)
            ):
                api_base = candidate.route_url.removesuffix("/chat/completions")
                existing = query(
                    """SELECT id::text
                       FROM llm_revolver_provider_sources
                       WHERE lower(api_base)=lower(%s)
                       LIMIT 1""",
                    (api_base,),
                    one=True,
                )
                source_id = str(existing.get("id") or "") if existing else ""
                if not source_id:
                    models_url = api_base.rstrip("/") + "/models"
                    created = query(
                        """INSERT INTO llm_revolver_provider_sources
                               (label, api_base, models_url, auth_mode, status, enabled)
                           VALUES (%s,%s,%s,'none','degraded',true)
                           RETURNING id::text""",
                        (
                            f"Scanner-Kandidat · {urllib.parse.urlsplit(api_base).hostname or 'unknown'}"[:120],
                            api_base,
                            models_url,
                        ),
                        one=True,
                        write=True,
                    ) or {}
                    source_id = str(created.get("id") or "")
                if source_id:
                    query(
                        """UPDATE llm_route_scanner_candidates
                           SET promoted_source_id=%s::uuid,
                               routing_eligible=true,
                               updated_at=NOW()
                           WHERE route_url=%s
                             AND status='canary_passed'
                             AND canary_confirmation_count=2
                             AND source_consensus=true""",
                        (source_id, candidate.route_url),
                        write=True,
                    )

    manager = RouteManager(
        acquire_lease=acquire_lease,
        release_lease=release_lease,
        persist_snapshot=persist_snapshot,
    )

    @app.route("/api/admin/llm/revolver-v3/route-scanner", methods=["GET"])
    @require_admin
    def admin_llm_route_scanner_status():
        latest = query(
            """SELECT id::text AS "runId", status,
                      source_count AS "sourceCount",
                      source_error_count AS "sourceErrorCount",
                      candidate_count AS "candidateCount",
                      canary_passed_count AS "canaryPassedCount",
                      blocked_count AS "blockedCount",
                      rejected_count AS "rejectedCount",
                      failure_family AS "failureFamily", evidence,
                      started_at AS "startedAt", completed_at AS "completedAt"
               FROM llm_route_scanner_runs
               ORDER BY started_at DESC LIMIT 1""",
            one=True,
        ) or {}
        counts = query(
            """SELECT
                   COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE status='canary_passed')::int AS canary_passed,
                   COUNT(*) FILTER (WHERE status='blocked')::int AS blocked,
                   COUNT(*) FILTER (WHERE routing_eligible=true)::int AS routing_eligible,
                   COUNT(*) FILTER (WHERE source_consensus=true)::int AS source_consensus,
                   COUNT(*) FILTER (WHERE promoted_source_id IS NOT NULL)::int AS promoted
               FROM llm_route_scanner_candidates""",
            one=True,
        ) or {}
        candidates = query(
            """SELECT route_url AS "routeUrl", host, status,
                      canary_confirmation_count AS "canaryConfirmationCount",
                      last_http_status AS "lastHttpStatus",
                      last_failure_family AS "lastFailureFamily",
                      last_latency_ms AS "lastLatencyMs",
                      free_quota_evidence AS "freeQuotaEvidence",
                      source_consensus AS "sourceConsensus",
                      routing_eligible AS "routingEligible",
                      promoted_source_id::text AS "promotedSourceId",
                      last_checked_at AS "lastCheckedAt"
               FROM llm_route_scanner_candidates
               ORDER BY (status='canary_passed') DESC, last_checked_at DESC
               LIMIT 50"""
        ) or []
        return jsonify({
            "ok": True,
            "status": "LLM_ROUTE_SCANNER_STATUS",
            "enabled": os.getenv("SOVEREIGN_LLM_ROUTE_SCANNER_ENABLED", "0").strip() == "1",
            "isScanningInThisWorker": manager.is_scanning,
            "intervalSeconds": _bounded_env_int(
                "SOVEREIGN_LLM_ROUTE_SCANNER_INTERVAL_SECONDS",
                _DEFAULT_SCAN_INTERVAL_SECONDS,
                300,
                86_400,
            ),
            "latestRun": dict(latest),
            "candidateCounts": {
                "total": int(counts.get("total") or 0),
                "canaryPassed": int(counts.get("canary_passed") or 0),
                "blocked": int(counts.get("blocked") or 0),
                "routingEligible": int(counts.get("routing_eligible") or 0),
                "sourceConsensus": int(counts.get("source_consensus") or 0),
                "promotedToDisabledOnboarding": int(counts.get("promoted") or 0),
            },
            "candidates": [dict(row) for row in candidates],
            "extractionPolicy": _EXTRACTION_POLICY,
            "sentenceDerivedEndpointsAccepted": False,
            "openRouterExcluded": True,
            "pricingFieldsParsed": False,
            "scrapestackDependency": False,
            "sourceFetchContract": "direct bounded HTTPS with structured failures",
            "onboardingRule": "double-canary plus independent-source-consensus creates disabled provider only",
            "truthBoundary": "candidate evidence may enter disabled FreeLLM onboarding; managed credentials, quota contract, fresh double-canary and revision receipt remain mandatory before routing",
            "userPromptsForwarded": False,
            "rawProviderResponsesReturned": False,
        })

    @app.route("/api/admin/llm/revolver-v3/route-scanner/scan", methods=["POST"])
    @require_admin
    def admin_llm_route_scanner_trigger():
        manager.request_scan()
        audit("admin_llm_route_scanner_triggered", None, {
            "candidateOnly": True,
            "automaticRouteActivation": False,
            "userPromptsForwarded": False,
        })
        return jsonify({
            "ok": True,
            "status": "LLM_ROUTE_SCAN_REQUESTED",
            "candidateOnly": True,
            "automaticRouteActivation": False,
            "nextAction": "Status neu laden; nur separat verifizierte Provider dürfen in den Revolver gelangen.",
        }), 202

    if os.getenv("SOVEREIGN_LLM_ROUTE_SCANNER_ENABLED", "0").strip() == "1":
        manager.start()
    return manager
