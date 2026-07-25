"""Pure contracts for public FreeLLM discovery sources.

The source catalog is evidence, never routing truth.  It intentionally excludes
OpenRouter because Sovereign's OpenRouter transport belongs to the independent
paid-routing lane.  No price or cost fields are parsed here.  Productive routes
still require the managed FreeLLM catalog, real completion canaries, a distinct
quota scope and a revision-bound receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from typing import Any, Iterable


TEXT_SOURCE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "canonicalUrl": "https://github.com/open-free-llm-api/awesome-freellm-apis/blob/main/README.md",
        "fetchUrl": "https://raw.githubusercontent.com/open-free-llm-api/awesome-freellm-apis/main/README.md",
        "authority": "github:open-free-llm-api/awesome-freellm-apis",
        "sourceClass": "community-free-route-list",
    },
    {
        "canonicalUrl": "https://github.com/cheahjs/free-llm-api-resources/blob/main/README.md",
        "fetchUrl": "https://raw.githubusercontent.com/cheahjs/free-llm-api-resources/main/README.md",
        "authority": "github:cheahjs/free-llm-api-resources",
        "sourceClass": "community-free-route-list",
    },
    {
        "canonicalUrl": "https://github.com/amardeeplakshkar/awesome-free-llm-apis/blob/main/README.md",
        "fetchUrl": "https://raw.githubusercontent.com/amardeeplakshkar/awesome-free-llm-apis/main/README.md",
        "authority": "github:amardeeplakshkar/awesome-free-llm-apis",
        "sourceClass": "community-free-route-list",
    },
    {
        "canonicalUrl": "https://github.com/zukixa/cool-ai-stuff/blob/main/README.md",
        "fetchUrl": "https://raw.githubusercontent.com/zukixa/cool-ai-stuff/main/README.md",
        "authority": "github:zukixa/cool-ai-stuff",
        "sourceClass": "community-free-route-list",
    },
    {
        "canonicalUrl": "https://github.com/mnfst/awesome-free-llm-apis/blob/main/README.md",
        "fetchUrl": "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/refs/heads/main/README.md",
        "authority": "github:mnfst/awesome-free-llm-apis",
        "sourceClass": "maintained-free-quota-catalog",
    },
    {
        "canonicalUrl": "https://github.com/AnonymoDGH/ultimate-free-llm-resources/blob/main/README.md",
        "fetchUrl": "https://raw.githubusercontent.com/AnonymoDGH/ultimate-free-llm-resources/refs/heads/main/README.md",
        "authority": "github:AnonymoDGH/ultimate-free-llm-resources",
        "sourceClass": "free-and-trial-resource-catalog",
    },
)

STRUCTURED_SOURCE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "canonicalUrl": "https://github.com/mnfst/awesome-free-llm-apis/blob/main/data.json",
        "fetchUrl": "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/refs/heads/main/data.json",
        "authority": "github:mnfst/awesome-free-llm-apis",
        "sourceClass": "maintained-free-quota-catalog",
        "format": "mnfst-data-json",
    },
)

ARCHITECTURE_REFERENCE_SOURCES: tuple[dict[str, str], ...] = (
    {
        "canonicalUrl": "https://github.com/yenanjing/awesome-model-routing",
        "authority": "github:yenanjing/awesome-model-routing",
        "use": "routing taxonomy and candidate-system review only",
    },
    {
        "canonicalUrl": "https://apilayer.com/products/scrapestack/",
        "authority": "vendor:apilayer/scrapestack",
        "use": "source-fetch retry/error patterns only; never routing truth",
    },
)

_FULL_ENDPOINT_RE = re.compile(
    r"https?://[a-zA-Z0-9.-]+(?::\d+)?(?:/[\w.-]+)*/v1/chat/completions"
)
_DENIED_PROVIDER_HOSTS = {
    "api.openai.com",
    "openai.com",
    "api.anthropic.com",
    "anthropic.com",
    "openrouter.ai",
    "api.openrouter.ai",
}
_TRIAL_MARKERS = (
    "trial credit",
    "signup credit",
    "one-time",
    "expires",
    "expiration",
    "prior spend",
    "top-up",
    "pay-as-you-go",
    "paid plan",
)
_FREE_MARKERS = (
    "permanent free",
    "permanently free",
    "forever free",
    "free tier",
    "no registration",
    "no credit card",
    "without credit card",
)
_ALLOWED_OPENAI_BASE_SUFFIXES = (
    "/v1",
    "/api/v1",
    "/openai/v1",
    "/compatible-mode/v1",
    "/api/gateway",
)


def canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def source_spec_by_fetch_url(fetch_url: str) -> dict[str, Any] | None:
    for spec in (*TEXT_SOURCE_SPECS, *STRUCTURED_SOURCE_SPECS):
        if str(spec["fetchUrl"]) == str(fetch_url):
            return dict(spec)
    return None


def source_authority(source_identity: str) -> str:
    identity = str(source_identity or "").strip()
    if identity == "seed":
        return "seed"
    spec = source_spec_by_fetch_url(identity)
    if spec:
        return str(spec["authority"])
    for spec in (*TEXT_SOURCE_SPECS, *STRUCTURED_SOURCE_SPECS):
        if identity == str(spec["canonicalUrl"]):
            return str(spec["authority"])
    parsed = urllib.parse.urlsplit(identity)
    return f"host:{(parsed.hostname or identity).casefold()}"


def independent_source_consensus(source_identities: Iterable[str]) -> bool:
    authorities = {
        source_authority(item)
        for item in source_identities
        if str(item or "").strip()
    }
    public = {item for item in authorities if item != "seed"}
    return len(public) >= 2 or ("seed" in authorities and len(public) >= 1)


def explicit_completion_endpoints(text: str) -> list[str]:
    """Return only completion endpoints literally present in source text."""
    return sorted(set(_FULL_ENDPOINT_RE.findall(str(text or ""))))


def _structured_completion_endpoint(base_url: Any) -> str:
    candidate = str(base_url or "").strip().rstrip("/")
    if not candidate:
        raise ValueError("structured_base_url_missing")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("structured_base_url_invalid")
    host = parsed.hostname.rstrip(".").casefold()
    if host in _DENIED_PROVIDER_HOSTS:
        raise ValueError("structured_provider_excluded")
    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    if not any(path.endswith(suffix) for suffix in _ALLOWED_OPENAI_BASE_SUFFIXES):
        raise ValueError("structured_openai_compatible_path_required")
    return urllib.parse.urlunsplit(
        ("https", host, f"{path}/chat/completions", "", "")
    )


def _permanent_free_quota_claim(provider: dict[str, Any]) -> bool:
    name = str(provider.get("name") or "").strip().casefold()
    base_url = str(provider.get("baseUrl") or "").strip().casefold()
    description = str(provider.get("description") or "").strip().casefold()
    if name == "openrouter" or "openrouter" in base_url:
        return False
    if any(marker in description for marker in _TRIAL_MARKERS):
        return False
    return any(marker in description for marker in _FREE_MARKERS)


def _bounded_models(provider: dict[str, Any]) -> list[dict[str, Any]]:
    models = provider.get("models") if isinstance(provider.get("models"), list) else []
    result: list[dict[str, Any]] = []
    for raw in models[:100]:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or "").strip()
        if not model_id:
            continue
        rate_limit = str(raw.get("rateLimit") or "").strip()
        result.append({
            "modelId": model_id[:240],
            "rateLimit": rate_limit[:160] or None,
        })
    return result


def parse_mnfst_free_quota_catalog(
    payload: Any,
    *,
    source_url: str,
) -> tuple[list[dict[str, Any]], int]:
    """Parse permanent-free quota claims without reading price/cost fields."""
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, list):
        raise ValueError("structured_catalog_invalid")
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for raw_provider in providers[:500]:
        if not isinstance(raw_provider, dict) or not _permanent_free_quota_claim(raw_provider):
            rejected += 1
            continue
        try:
            endpoint = _structured_completion_endpoint(raw_provider.get("baseUrl"))
        except ValueError:
            rejected += 1
            continue
        evidence = {
            "schemaVersion": "sovereign.free-route-source-evidence.v1",
            "sourceUrl": str(source_url)[:500],
            "sourceAuthority": source_authority(source_url),
            "providerName": str(raw_provider.get("name") or "")[:120],
            "category": str(raw_provider.get("category") or "")[:80],
            "baseUrl": str(raw_provider.get("baseUrl") or "")[:500],
            "descriptionSha256": hashlib.sha256(
                str(raw_provider.get("description") or "").encode("utf-8")
            ).hexdigest(),
            "models": _bounded_models(raw_provider),
            "freeQuotaOnly": True,
            "pricingFieldsParsed": False,
            "costFieldsParsed": False,
            "openRouterExcluded": True,
            "routingEligible": False,
        }
        evidence["evidenceSha256"] = canonical_sha256(evidence)
        accepted.append({"endpoint": endpoint, "evidence": evidence})
    return accepted, rejected
