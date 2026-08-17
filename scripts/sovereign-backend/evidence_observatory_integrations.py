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
from typing import Any

from evidence_observatory_contracts import canonical_json, normalized_claim, safe_json_value, sha256_text

NOTION_VERSION = "2026-03-11"


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


def publish_huggingface_batch(*, rows: list[dict[str, Any]], repo_id: str, revision: str) -> dict[str, Any]:
    """Commit a gated batch and verify exact bytes at the returned Hub revision.

    Authentication is delegated to huggingface_hub's configured runtime identity;
    no credential value crosses this module's function boundary.
    """
    if not repo_id:
        raise RuntimeError("huggingface_repo_configuration_missing")
    target_revision = revision.strip() or "staging-atlas"
    if target_revision in {"main", "master"}:
        raise RuntimeError("huggingface_direct_main_publish_forbidden")
    if not rows:
        raise RuntimeError("huggingface_publish_empty_batch")
    try:
        from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub_dependency_missing") from exc

    import uuid
    batch_id = str(uuid.uuid4())
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data_path = f"staging/atlas-batches/{stamp}-{batch_id}.jsonl"
    manifest_path = f"staging/atlas-batches/{stamp}-{batch_id}.manifest.json"
    data_bytes = ("\n".join(canonical_json(row) for row in rows) + "\n").encode("utf-8")
    expected_data_sha = hashlib.sha256(data_bytes).hexdigest()
    manifest = {
        "schemaVersion": "sovereign.evidence-hf-batch.v1",
        "batchId": batch_id,
        "caseIds": [row.get("caseId") for row in rows],
        "caseCount": len(rows),
        "dataPath": data_path,
        "dataSha256": expected_data_sha,
        "truthNotice": "Publication means the evidence state passed deterministic gates; it does not imply every claim is SUPPORTED.",
    }
    manifest_bytes = canonical_json(manifest).encode("utf-8")
    expected_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    api = HfApi()
    try:
        api.create_branch(repo_id=repo_id, repo_type="dataset", branch=target_revision, exist_ok=True)
    except Exception:
        # Existing branch and permission errors are decided by create_commit below.
        pass
    commit = api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        revision=target_revision,
        operations=[
            CommitOperationAdd(path_in_repo=data_path, path_or_fileobj=data_bytes),
            CommitOperationAdd(path_in_repo=manifest_path, path_or_fileobj=manifest_bytes),
        ],
        commit_message=f"Sovereign Evidence Atlas batch {batch_id}",
    )
    commit_oid = str(getattr(commit, "oid", "") or getattr(commit, "commit_id", "") or "")
    if not commit_oid:
        raise RuntimeError("huggingface_commit_oid_missing")
    data_local = hf_hub_download(repo_id=repo_id, filename=data_path, repo_type="dataset", revision=commit_oid)
    manifest_local = hf_hub_download(repo_id=repo_id, filename=manifest_path, repo_type="dataset", revision=commit_oid)
    with open(data_local, "rb") as handle:
        observed_data_sha = hashlib.sha256(handle.read()).hexdigest()
    with open(manifest_local, "rb") as handle:
        observed_manifest_sha = hashlib.sha256(handle.read()).hexdigest()
    if observed_data_sha != expected_data_sha or observed_manifest_sha != expected_manifest_sha:
        raise RuntimeError("huggingface_publish_readback_mismatch")
    return {
        "ok": True,
        "batchId": batch_id,
        "repoId": repo_id,
        "revision": target_revision,
        "commitOid": commit_oid,
        "dataPath": data_path,
        "manifestPath": manifest_path,
        "dataSha256": expected_data_sha,
        "manifestSha256": expected_manifest_sha,
        "readbackVerified": True,
        "runtimeIdentityUsed": True,
    }


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
