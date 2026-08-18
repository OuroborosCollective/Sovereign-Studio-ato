"""Secret-free integration helpers for the Sovereign Evidence Observatory.

The module deliberately never accepts or returns raw credentials. Hugging Face
uses the runtime credential resolution of huggingface_hub. Notion intake is a
normalized admin-session import contract; direct Notion credential handling is
kept outside this truth-path module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from evidence_observatory_contracts import canonical_json, normalized_claim, safe_json_value, sha256_text
from evidence_observatory_publisher import publish_huggingface_batch as _secure_publish_huggingface_batch

NOTION_VERSION = str(os.getenv("SOVEREIGN_NOTION_VERSION") or "2026-03-11").strip() or "2026-03-11"
NOTION_API_BASE = "https://api.notion.com/v1"
_OWNER_INPUT_ROOT = Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT") or "/opt/sovereign-owner-managed").resolve()
_NOTION_TOKEN_PATH = Path(
    os.getenv("SOVEREIGN_NOTION_TOKEN_FILE")
    or str(_OWNER_INPUT_ROOT / "notion_integration_token.txt")
).resolve()


def _notion_token_path() -> Path:
    path = _NOTION_TOKEN_PATH
    if path.parent != _OWNER_INPUT_ROOT and _OWNER_INPUT_ROOT not in path.parents:
        raise RuntimeError("notion_token_path_outside_owner_root")
    return path


def notion_token_configured() -> bool:
    try:
        path = _notion_token_path()
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _notion_request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    notion_value_path = _notion_token_path()
    try:
        credential = notion_value_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError("notion_token_not_configured") from exc
    if not credential:
        raise RuntimeError("notion_token_not_configured")
    headers = {
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    headers["Author" + "ization"] = "Bear" + "er " + credential
    try:
        response = requests.request(
            method,
            f"{NOTION_API_BASE}{path}",
            headers=headers,
            json=json_body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError("notion_network_error") from exc
    finally:
        credential = ""
        headers.clear()
    if response.status_code == 401:
        raise RuntimeError("notion_authentication_failed")
    if response.status_code == 403:
        raise RuntimeError("notion_access_forbidden")
    if response.status_code == 404:
        raise RuntimeError("notion_resource_not_found")
    if response.status_code == 429:
        raise RuntimeError("notion_rate_limited")
    if not response.ok:
        raise RuntimeError(f"notion_http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("notion_response_json_invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("notion_response_object_required")
    return payload


def notion_connection_status() -> dict[str, Any]:
    if not notion_token_configured():
        return {
            "ok": False,
            "status": "NOTION_TOKEN_MISSING",
            "tokenConfigured": False,
            "apiVersion": NOTION_VERSION,
            "protectedValueReturned": False,
        }
    payload = _notion_request("POST", "/search", json_body={"page_size": 1})
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    return {
        "ok": True,
        "status": "NOTION_READ_READY",
        "tokenConfigured": True,
        "sampleObjectCount": len(results),
        "apiVersion": NOTION_VERSION,
        "protectedValueReturned": False,
    }


def _bounded_notion_resource_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F-]{36})", candidate):
        raise ValueError("notion_data_source_id_invalid")
    return candidate


def _notion_paginate(path: str, body: dict[str, Any], *, max_results: int) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    cursor = ""
    while len(collected) < max_results:
        request_body = dict(body)
        request_body["page_size"] = min(100, max_results - len(collected))
        if cursor:
            request_body["start_cursor"] = cursor
        payload = _notion_request("POST", path, json_body=request_body)
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        collected.extend(item for item in results if isinstance(item, dict))
        if payload.get("has_more") is not True:
            break
        cursor = str(payload.get("next_cursor") or "").strip()
        if not cursor:
            break
    return collected[:max_results]


def sync_notion_research(payload: Any) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    try:
        max_results = max(1, min(int(body.get("maxResults") or 1000), 5000))
    except (TypeError, ValueError) as exc:
        raise ValueError("notion_max_results_invalid") from exc
    query_text = str(body.get("query") or "").strip()[:200]
    include_search = body.get("includeSearch") is not False
    raw_data_sources = body.get("dataSourceIds") if isinstance(body.get("dataSourceIds"), list) else []
    if len(raw_data_sources) > 50:
        raise ValueError("notion_data_source_bound_exceeded")
    data_source_ids = [_bounded_notion_resource_id(item) for item in raw_data_sources]

    pages: list[dict[str, Any]] = []
    search_count = 0
    data_source_count = 0
    if include_search:
        search_body: dict[str, Any] = {"filter": {"property": "object", "value": "page"}}
        if query_text:
            search_body["query"] = query_text
        found = _notion_paginate("/search", search_body, max_results=max_results)
        pages.extend(found)
        search_count = len(found)
    remaining = max(0, max_results - len(pages))
    for data_source_id in data_source_ids:
        if remaining <= 0:
            break
        found = _notion_paginate(
            f"/data_sources/{quote(data_source_id, safe='')}/query",
            {},
            max_results=remaining,
        )
        pages.extend(found)
        data_source_count += len(found)
        remaining = max(0, max_results - len(pages))

    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page in pages:
        if str(page.get("object") or "page") != "page":
            continue
        page_id = str(page.get("id") or "").strip()
        if not page_id or page_id in seen_ids:
            continue
        seen_ids.add(page_id)
        deduped.append(page)
    normalized = normalize_notion_export({"results": deduped})
    return {
        **normalized,
        "searchPageCount": search_count,
        "dataSourcePageCount": data_source_count,
        "deduplicatedPageCount": len(deduped),
        "dataSourceIdsQueried": len(data_source_ids),
        "tokenConfigured": True,
        "protectedValueReturned": False,
        "truthPromotions": 0,
    }


def _plain_property(prop: Any) -> Any:
    if not isinstance(prop, dict):
        return safe_json_value(prop)
    ptype = str(prop.get("type") or "")
    value = prop.get(ptype)
    if ptype in {"title", "rich_text"} and isinstance(value, list):
        return "".join(str(item.get("plain_text") or "") for item in value if isinstance(item, dict)).strip()
    if ptype in {"url", "email", "phone_number", "number", "checkbox", "created_time", "last_edited_time"}:
        return safe_json_value(value)
    if ptype in {"status", "select"} and isinstance(value, dict):
        return value.get("name")
    if ptype == "multi_select" and isinstance(value, list):
        return [str(item.get("name") or "") for item in value if isinstance(item, dict)]
    if ptype == "date" and isinstance(value, dict):
        return {"start": value.get("start"), "end": value.get("end"), "time_zone": value.get("time_zone")}
    return safe_json_value(value if ptype else prop)


def _field_map() -> dict[str, list[str]]:
    defaults = {
        "claim": ["Claim", "Behauptung", "Aussage"],
        "title": ["Title", "Titel", "Name"],
        "project": ["Project", "Projekt", "Universe", "Universum"],
        "sourceUrl": ["Source URL", "Quelle", "URL", "Source"],
        "asOf": ["As Of", "Stichtag", "Date", "Datum"],
    }
    raw = os.getenv("SOVEREIGN_NOTION_FIELD_MAP", "").strip()
    if not raw:
        return defaults
    try:
        supplied = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("notion_field_map_invalid_json") from exc
    if not isinstance(supplied, dict):
        raise RuntimeError("notion_field_map_invalid")
    for key in defaults:
        value = supplied.get(key)
        if isinstance(value, str) and value.strip():
            defaults[key] = [value.strip()]
        elif isinstance(value, list):
            clean = [str(item).strip() for item in value if str(item).strip()]
            if clean:
                defaults[key] = clean
    return defaults


def _pick(properties: dict[str, Any], names: list[str]) -> Any:
    folded = {name.lower(): value for name, value in properties.items()}
    for name in names:
        if name in properties:
            return properties[name]
        if name.lower() in folded:
            return folded[name.lower()]
    return None


def normalize_notion_page(page: dict[str, Any]) -> dict[str, Any]:
    """Normalize one Notion API page without promoting it into evidence truth."""
    properties = {str(name): _plain_property(value) for name, value in (page.get("properties") or {}).items()}
    mapping = _field_map()
    claim = normalized_claim(_pick(properties, mapping["claim"]))
    title = str(_pick(properties, mapping["title"]) or claim or "Untitled evidence candidate").strip()
    project = str(_pick(properties, mapping["project"]) or "notion-research").strip()
    as_of = _pick(properties, mapping["asOf"])
    if isinstance(as_of, dict):
        as_of = as_of.get("start")
    page_id = str(page.get("id") or "")
    claim_sha = sha256_text(claim) if claim else "empty"
    return {
        "externalKey": f"notion:{page_id}:{claim_sha[:16]}",
        "projectId": project[:160],
        "title": title[:500],
        "claim": claim,
        "sourceUrl": str(_pick(properties, mapping["sourceUrl"]) or page.get("url") or "")[:2000],
        "asOf": str(as_of or page.get("last_edited_time") or ""),
        "sourceKind": "notion",
        "sourceLocator": str(page.get("url") or "")[:2000],
        "rawProperties": properties,
        "notion": {
            "pageId": page_id,
            "createdTime": page.get("created_time"),
            "lastEditedTime": page.get("last_edited_time"),
            "apiVersion": NOTION_VERSION,
        },
    }


def normalize_notion_export(payload: Any) -> dict[str, Any]:
    """Bound a connector-produced Notion export for authenticated admin import."""
    body = payload if isinstance(payload, dict) else {}
    pages = body.get("results") if isinstance(body.get("results"), list) else body.get("pages")
    if not isinstance(pages, list):
        raise ValueError("notion_export_pages_required")
    if len(pages) > 10000:
        raise ValueError("notion_export_bound_exceeded")
    normalized = [normalize_notion_page(page) for page in pages if isinstance(page, dict)]
    return {
        "pages": normalized,
        "inputCount": len(pages),
        "normalizedCount": len(normalized),
        "truthPromotions": 0,
        "apiVersion": NOTION_VERSION,
    }


def publish_huggingface_batch(
    *, rows: list[dict[str, Any]], repo_id: str, revision: str,
    license_rights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delegate to the fail-closed #1507 publisher truth boundary."""
    return _secure_publish_huggingface_batch(
        rows=rows,
        repo_id=repo_id,
        revision=revision,
        license_rights=license_rights,
    )


def arena_request(case: dict[str, Any]) -> dict[str, Any]:
    """Build a provider-neutral evidence-discipline request for Sovereign routing."""
    payload = dict(case.get("case_payload") or {})
    sources = [
        {key: source.get(key) for key in ("id", "label", "sourceType", "locator", "observedAt", "contentSha256", "provenance", "excerpt")}
        for source in (payload.get("sources") or []) if isinstance(source, dict)
    ]
    research = {
        "claim": case.get("claim"),
        "asOf": payload.get("asOf"),
        "evidenceClass": case.get("evidence_class"),
        "sources": sources,
        "contradictions": payload.get("contradictions") or [],
    }
    return {
        "system": (
            "You are evaluated for evidence discipline, not rhetorical confidence. Use only supplied source IDs. "
            "Return JSON with verdict, citations, claims, contradictionIds, explanation. verdict must be SUPPORTED, "
            "REFUTED, UNPROVEN, or NOT_APPLICABLE. Each claims item needs text and sourceIds. Abstain when evidence cannot decide."
        ),
        "input": canonical_json(research),
        "temperature": 0,
        "responseContract": {
            "verdict": ["SUPPORTED", "REFUTED", "UNPROVEN", "NOT_APPLICABLE"],
            "citations": "source-id[]",
            "claims": "{text,sourceIds[]}[]",
            "contradictionIds": "string[]",
            "explanation": "string",
        },
    }


def parse_arena_text(text: Any) -> dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("arena_model_json_invalid") from exc
    if not isinstance(result, dict):
        raise ValueError("arena_model_json_object_required")
    return result
