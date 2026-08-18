"""Quarantined OmniRoute free-model catalog sensor for Sovereign.

OmniRoute is never an execution transport or routing authority here. This module
reads one public catalog at an exact upstream revision, verifies the Git blob
identity, persists bounded candidate metadata, and keeps routing eligibility
hard-false. Promotion remains owned by Sovereign's direct provider onboarding,
real double-canary, quota and receipt gates.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import requests
from flask import jsonify

_SENSOR_ID = "omniroute-free-model-catalog"
_SOURCE_REPOSITORY = "diegosouzapw/OmniRoute"
_SOURCE_REF = "release/v3.8.50"
_SOURCE_PATH = "open-sse/config/freeModelCatalog.data.ts"
_GITHUB_API = "https://api.github.com"
_MAX_SOURCE_BYTES = 3_000_000
_MAX_CANDIDATES = 5_000
_DEFAULT_INTERVAL_SECONDS = 21_600
_DEFAULT_INITIAL_DELAY_SECONDS = 60
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_BLOB_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CURATED_RE = re.compile(r'^export const FREE_CATALOG_CURATED_AT = "(\d{4}-\d{2}-\d{2})";$')
_FREE_TYPES = frozenset({
    "recurring-daily",
    "recurring-monthly",
    "recurring-credit",
    "recurring-uncapped",
    "one-time-initial",
    "keyless",
    "discontinued",
})
_TOS_VERDICTS = frozenset({"ok", "caution", "ambiguous", "avoid", "unknown"})


class OmniRouteRadarError(RuntimeError):
    """Typed, secret-free radar failure."""

    def __init__(self, family: str) -> None:
        super().__init__(family)
        self.family = str(family)[:160]


@dataclass(frozen=True, slots=True)
class CatalogSource:
    revision: str
    blob_sha: str
    content_sha256: str
    curated_at: str | None
    text: str


@dataclass(frozen=True, slots=True)
class RadarCandidate:
    candidate_sha256: str
    provider_id: str
    model_id: str
    display_name: str
    pool_key: str | None
    free_type: str
    tos_verdict: str
    trains_on_prompts: bool | None
    monthly_tokens: int
    credit_tokens: int
    status: str


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json_response(response: Any, *, limit: int) -> dict[str, Any]:
    declared = int(response.headers.get("Content-Length") or 0)
    if declared > limit:
        raise OmniRouteRadarError("omniroute_response_too_large")
    raw = bytes(response.content or b"")
    if len(raw) > limit:
        raise OmniRouteRadarError("omniroute_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OmniRouteRadarError("omniroute_response_invalid") from exc
    if not isinstance(payload, dict):
        raise OmniRouteRadarError("omniroute_response_invalid")
    return payload


def _github_get(path: str, *, timeout: int = 20) -> dict[str, Any]:
    url = f"{_GITHUB_API.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sovereign-omniroute-radar/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
    except requests.Timeout as exc:
        raise OmniRouteRadarError("omniroute_github_timeout") from exc
    except requests.RequestException as exc:
        raise OmniRouteRadarError("omniroute_github_unavailable") from exc
    if response.status_code != 200:
        if response.status_code == 403:
            raise OmniRouteRadarError("omniroute_github_rate_limited_or_forbidden")
        raise OmniRouteRadarError(f"omniroute_github_http_{response.status_code}")
    return _read_json_response(response, limit=_MAX_SOURCE_BYTES + 500_000)


def fetch_catalog_source() -> CatalogSource:
    commit = _github_get(
        f"repos/{_SOURCE_REPOSITORY}/commits/{_SOURCE_REF}",
        timeout=20,
    )
    revision = str(commit.get("sha") or "").strip().lower()
    if not _SOURCE_REVISION_RE.fullmatch(revision):
        raise OmniRouteRadarError("omniroute_source_revision_invalid")

    contents = _github_get(
        f"repos/{_SOURCE_REPOSITORY}/contents/{_SOURCE_PATH}?ref={revision}",
        timeout=20,
    )
    if contents.get("type") != "file" or contents.get("encoding") != "base64":
        raise OmniRouteRadarError("omniroute_source_content_contract_invalid")
    blob_sha = str(contents.get("sha") or "").strip().lower()
    if not _BLOB_SHA_RE.fullmatch(blob_sha):
        raise OmniRouteRadarError("omniroute_source_blob_sha_invalid")
    encoded = str(contents.get("content") or "").replace("\n", "")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise OmniRouteRadarError("omniroute_source_base64_invalid") from exc
    if not raw or len(raw) > _MAX_SOURCE_BYTES:
        raise OmniRouteRadarError("omniroute_source_size_invalid")
    if _git_blob_sha1(raw) != blob_sha:
        raise OmniRouteRadarError("omniroute_source_blob_readback_mismatch")
    content_sha256 = hashlib.sha256(raw).hexdigest()
    if not _SHA256_RE.fullmatch(content_sha256):
        raise OmniRouteRadarError("omniroute_source_sha256_invalid")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OmniRouteRadarError("omniroute_source_utf8_invalid") from exc

    curated_at: str | None = None
    for line in text.splitlines():
        match = _CURATED_RE.fullmatch(line.strip())
        if match:
            try:
                curated_at = date.fromisoformat(match.group(1)).isoformat()
            except ValueError as exc:
                raise OmniRouteRadarError("omniroute_curated_date_invalid") from exc
            break
    if curated_at is None:
        raise OmniRouteRadarError("omniroute_curated_date_missing")
    return CatalogSource(
        revision=revision,
        blob_sha=blob_sha,
        content_sha256=content_sha256,
        curated_at=curated_at,
        text=text,
    )


def _parse_ts_object_line(line: str) -> dict[str, Any]:
    body = line.strip().rstrip(",")
    if not body.startswith("{ provider:") or not body.endswith("}"):
        raise OmniRouteRadarError("omniroute_catalog_entry_shape_invalid")
    json_like = re.sub(
        r'([,{]\s*)([A-Za-z_][A-Za-z0-9_]*):',
        r'\1"\2":',
        body,
    )
    try:
        payload = json.loads(json_like)
    except json.JSONDecodeError as exc:
        raise OmniRouteRadarError("omniroute_catalog_entry_parse_failed") from exc
    if not isinstance(payload, dict):
        raise OmniRouteRadarError("omniroute_catalog_entry_shape_invalid")
    return payload


def parse_catalog(source: CatalogSource) -> list[RadarCandidate]:
    entry_lines = [
        line for line in source.text.splitlines()
        if line.strip().startswith("{ provider:")
    ]
    if not entry_lines or len(entry_lines) > _MAX_CANDIDATES:
        raise OmniRouteRadarError("omniroute_catalog_candidate_count_invalid")

    candidates: list[RadarCandidate] = []
    seen: set[tuple[str, str, str | None]] = set()
    for line in entry_lines:
        row = _parse_ts_object_line(line)
        provider = str(row.get("provider") or "").strip()
        model_id = str(row.get("modelId") or "").strip()
        display_name = str(row.get("displayName") or "").strip()
        pool_raw = row.get("poolKey")
        pool_key = None if pool_raw is None else str(pool_raw).strip()
        free_type = str(row.get("freeType") or "").strip()
        tos = str(row.get("tos") or "unknown").strip()
        trains = row.get("trainsOnPrompts")
        monthly = row.get("monthlyTokens")
        credits = row.get("creditTokens")
        if not (
            1 <= len(provider) <= 120
            and 1 <= len(model_id) <= 300
            and 1 <= len(display_name) <= 400
            and (pool_key is None or 1 <= len(pool_key) <= 180)
            and free_type in _FREE_TYPES
            and tos in _TOS_VERDICTS
            and (trains is None or isinstance(trains, bool))
            and isinstance(monthly, int)
            and not isinstance(monthly, bool)
            and 0 <= monthly <= 10**15
            and isinstance(credits, int)
            and not isinstance(credits, bool)
            and 0 <= credits <= 10**15
        ):
            raise OmniRouteRadarError("omniroute_catalog_entry_contract_invalid")
        identity = (provider, model_id, pool_key)
        if identity in seen:
            raise OmniRouteRadarError("omniroute_catalog_duplicate_identity")
        seen.add(identity)
        candidate_sha256 = _canonical_sha256({
            "schemaVersion": "sovereign.provider-radar-candidate.v1",
            "sensorId": _SENSOR_ID,
            "providerId": provider,
            "modelId": model_id,
            "poolKey": pool_key,
        })
        candidates.append(RadarCandidate(
            candidate_sha256=candidate_sha256,
            provider_id=provider,
            model_id=model_id,
            display_name=display_name,
            pool_key=pool_key,
            free_type=free_type,
            tos_verdict=tos,
            trains_on_prompts=trains,
            monthly_tokens=monthly,
            credit_tokens=credits,
            status="blocked_tos" if tos == "avoid" else "quarantined",
        ))
    return candidates


class OmniRouteProviderRadar:
    def __init__(self, *, query: Callable[..., Any], audit: Callable[..., Any]) -> None:
        self._query = query
        self._audit = audit
        self._scan_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lease_owner = str(uuid.uuid4())

    def _acquire_lease(self) -> bool:
        lease_seconds = max(120, min(self.interval_seconds, 3_600))
        row = self._query(
            """UPDATE llm_provider_radar_runtime
               SET lease_owner=%s::uuid,
                   lease_expires_at=NOW() + (%s * INTERVAL '1 second'),
                   updated_at=NOW()
               WHERE sensor_id=%s
                 AND (lease_expires_at IS NULL OR lease_expires_at < NOW() OR lease_owner=%s::uuid)
               RETURNING sensor_id""",
            (self._lease_owner, lease_seconds, _SENSOR_ID, self._lease_owner),
            one=True,
            write=True,
        )
        return bool(row)

    def _release_lease(self) -> None:
        self._query(
            """UPDATE llm_provider_radar_runtime
               SET lease_owner=NULL, lease_expires_at=NULL, updated_at=NOW()
               WHERE sensor_id=%s AND lease_owner=%s::uuid""",
            (_SENSOR_ID, self._lease_owner),
            write=True,
        )

    @property
    def interval_seconds(self) -> int:
        return _bounded_env_int(
            "SOVEREIGN_OMNIROUTE_RADAR_INTERVAL_SECONDS",
            _DEFAULT_INTERVAL_SECONDS,
            900,
            86_400,
        )

    def scan_once(self) -> dict[str, Any]:
        if not self._scan_lock.acquire(blocking=False):
            return {"ok": False, "status": "busy", "sensorId": _SENSOR_ID}
        run_id = str(uuid.uuid4())
        started = time.time()
        source: CatalogSource | None = None
        candidate_count = quarantined_count = blocked_count = rejected_count = 0
        failure_family: str | None = None
        try:
            source = fetch_catalog_source()
            candidates = parse_catalog(source)
            candidate_count = len(candidates)
            blocked_count = sum(1 for item in candidates if item.status == "blocked_tos")
            quarantined_count = candidate_count - blocked_count

            self._query(
                """UPDATE llm_provider_radar_candidates
                   SET status='stale', updated_at=NOW()
                   WHERE sensor_id=%s AND source_revision <> %s""",
                (_SENSOR_ID, source.revision),
                write=True,
            )
            for item in candidates:
                metadata = {
                    "schemaVersion": "sovereign.omniroute-radar-candidate-metadata.v1",
                    "catalogOnly": True,
                    "runtimeVerified": False,
                    "automaticRouteActivation": False,
                    "promotionRequiresDirectSource": True,
                    "promotionRequiresRealDoubleCanary": True,
                    "rawCatalogPersisted": False,
                }
                self._query(
                    """INSERT INTO llm_provider_radar_candidates (
                           candidate_sha256, sensor_id, provider_id, model_id,
                           display_name, pool_key, free_type, tos_verdict,
                           trains_on_prompts, monthly_tokens, credit_tokens,
                           source_revision, source_blob_sha, source_content_sha256,
                           source_curated_at, status, routing_eligible,
                           promotion_requires_direct_canary, metadata,
                           first_seen_at, last_seen_at, updated_at
                       ) VALUES (
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::date,
                           %s,false,true,%s::jsonb,NOW(),NOW(),NOW()
                       )
                       ON CONFLICT (candidate_sha256) DO UPDATE SET
                           display_name=EXCLUDED.display_name,
                           free_type=EXCLUDED.free_type,
                           tos_verdict=EXCLUDED.tos_verdict,
                           trains_on_prompts=EXCLUDED.trains_on_prompts,
                           monthly_tokens=EXCLUDED.monthly_tokens,
                           credit_tokens=EXCLUDED.credit_tokens,
                           source_revision=EXCLUDED.source_revision,
                           source_blob_sha=EXCLUDED.source_blob_sha,
                           source_content_sha256=EXCLUDED.source_content_sha256,
                           source_curated_at=EXCLUDED.source_curated_at,
                           status=EXCLUDED.status,
                           routing_eligible=false,
                           promotion_requires_direct_canary=true,
                           metadata=EXCLUDED.metadata,
                           last_seen_at=NOW(), updated_at=NOW()""",
                    (
                        item.candidate_sha256,
                        _SENSOR_ID,
                        item.provider_id,
                        item.model_id,
                        item.display_name,
                        item.pool_key,
                        item.free_type,
                        item.tos_verdict,
                        item.trains_on_prompts,
                        item.monthly_tokens,
                        item.credit_tokens,
                        source.revision,
                        source.blob_sha,
                        source.content_sha256,
                        source.curated_at,
                        item.status,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                    ),
                    write=True,
                )
            evidence = {
                "schemaVersion": "sovereign.omniroute-provider-radar-run.v1",
                "sensorId": _SENSOR_ID,
                "sourceRepository": _SOURCE_REPOSITORY,
                "sourceRef": _SOURCE_REF,
                "sourceRevision": source.revision,
                "sourcePath": _SOURCE_PATH,
                "sourceBlobSha": source.blob_sha,
                "sourceContentSha256": source.content_sha256,
                "sourceCuratedAt": source.curated_at,
                "candidateCount": candidate_count,
                "quarantinedCount": quarantined_count,
                "blockedTosCount": blocked_count,
                "routingEligibleCount": 0,
                "catalogIsRuntimeEvidence": False,
                "automaticRouteActivation": False,
                "promotionRequiresDirectProviderCanary": True,
                "rawCatalogPersisted": False,
                "secretValuesReturned": False,
            }
            evidence["evidenceSha256"] = _canonical_sha256(evidence)
            status = "completed"
            ok = True
        except OmniRouteRadarError as exc:
            failure_family = exc.family
            status = "failed"
            ok = False
            evidence = {
                "schemaVersion": "sovereign.omniroute-provider-radar-run.v1",
                "sensorId": _SENSOR_ID,
                "failureFamily": failure_family,
                "catalogIsRuntimeEvidence": False,
                "automaticRouteActivation": False,
                "secretValuesReturned": False,
            }
            evidence["evidenceSha256"] = _canonical_sha256(evidence)
        except Exception:
            failure_family = "omniroute_radar_unclassified_failure"
            status = "failed"
            ok = False
            evidence = {
                "schemaVersion": "sovereign.omniroute-provider-radar-run.v1",
                "sensorId": _SENSOR_ID,
                "failureFamily": failure_family,
                "catalogIsRuntimeEvidence": False,
                "automaticRouteActivation": False,
                "secretValuesReturned": False,
            }
            evidence["evidenceSha256"] = _canonical_sha256(evidence)
        finally:
            completed = time.time()
            self._query(
                """INSERT INTO llm_provider_radar_runs (
                       id, sensor_id, source_repository, source_ref, source_revision,
                       source_path, source_blob_sha, source_content_sha256, status,
                       candidate_count, quarantined_count, blocked_count, rejected_count,
                       failure_family, evidence, started_at, completed_at
                   ) VALUES (
                       %s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,
                       to_timestamp(%s),to_timestamp(%s)
                   )""",
                (
                    run_id,
                    _SENSOR_ID,
                    _SOURCE_REPOSITORY,
                    _SOURCE_REF,
                    source.revision if source else None,
                    _SOURCE_PATH,
                    source.blob_sha if source else None,
                    source.content_sha256 if source else None,
                    status,
                    candidate_count,
                    quarantined_count,
                    blocked_count,
                    rejected_count,
                    failure_family,
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")),
                    started,
                    completed,
                ),
                write=True,
            )
            self._scan_lock.release()
        return {
            "ok": ok,
            "status": status,
            "runId": run_id,
            "sensorId": _SENSOR_ID,
            "candidateCount": candidate_count,
            "quarantinedCount": quarantined_count,
            "blockedCount": blocked_count,
            "failureFamily": failure_family,
            "sourceRevision": source.revision if source else None,
            "routingEligibleCount": 0,
        }

    def _loop(self) -> None:
        initial = _bounded_env_int(
            "SOVEREIGN_OMNIROUTE_RADAR_INITIAL_DELAY_SECONDS",
            _DEFAULT_INITIAL_DELAY_SECONDS,
            5,
            3_600,
        )
        if self._stop.wait(initial):
            return
        while not self._stop.is_set():
            acquired = False
            try:
                acquired = self._acquire_lease()
                if acquired:
                    self.scan_once()
            except Exception:
                pass
            finally:
                if acquired:
                    try:
                        self._release_lease()
                    except Exception:
                        pass
            if self._stop.wait(self.interval_seconds):
                return

    def start(self) -> None:
        if os.getenv("SOVEREIGN_OMNIROUTE_RADAR_ENABLED", "1").strip() != "1":
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop,
            name="sovereign-omniroute-radar",
            daemon=True,
        )
        self._thread.start()


def register_omniroute_provider_radar(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    audit: Callable[..., Any],
) -> OmniRouteProviderRadar:
    radar = OmniRouteProviderRadar(query=query, audit=audit)

    @app.route("/api/admin/llm/provider-radar/omniroute", methods=["GET"])
    @require_admin
    def admin_omniroute_provider_radar_status():
        latest = query(
            """SELECT id::text AS id, status, source_revision AS "sourceRevision",
                      source_blob_sha AS "sourceBlobSha",
                      source_content_sha256 AS "sourceContentSha256",
                      candidate_count AS "candidateCount",
                      quarantined_count AS "quarantinedCount",
                      blocked_count AS "blockedCount",
                      failure_family AS "failureFamily",
                      started_at AS "startedAt", completed_at AS "completedAt"
               FROM llm_provider_radar_runs
               WHERE sensor_id=%s ORDER BY started_at DESC LIMIT 1""",
            (_SENSOR_ID,),
            one=True,
        ) or {}
        counts = query(
            """SELECT COUNT(*)::integer AS total,
                      COUNT(*) FILTER (WHERE status='quarantined')::integer AS quarantined,
                      COUNT(*) FILTER (WHERE status='blocked_tos')::integer AS blocked,
                      COUNT(*) FILTER (WHERE status='stale')::integer AS stale,
                      COUNT(*) FILTER (WHERE routing_eligible=true)::integer AS routing_eligible
               FROM llm_provider_radar_candidates WHERE sensor_id=%s""",
            (_SENSOR_ID,),
            one=True,
        ) or {}
        return jsonify({
            "ok": True,
            "sensorId": _SENSOR_ID,
            "truthBoundary": "catalog-metadata-only",
            "latestRun": dict(latest),
            "candidates": {
                "total": int(counts.get("total") or 0),
                "quarantined": int(counts.get("quarantined") or 0),
                "blocked": int(counts.get("blocked") or 0),
                "stale": int(counts.get("stale") or 0),
                "routingEligible": int(counts.get("routing_eligible") or 0),
            },
            "automaticRouteActivation": False,
            "promotionRequiresDirectProviderCanary": True,
        })

    @app.route("/api/admin/llm/provider-radar/omniroute/scan", methods=["POST"])
    @require_admin
    def admin_omniroute_provider_radar_scan():
        result = radar.scan_once()
        audit("admin_omniroute_provider_radar_scan", result.get("runId"), {
            "sensorId": _SENSOR_ID,
            "status": result.get("status"),
            "candidateCount": result.get("candidateCount"),
            "routingEligibleCount": 0,
        })
        return jsonify(result), 200 if result.get("ok") else 503

    radar.start()
    return radar
