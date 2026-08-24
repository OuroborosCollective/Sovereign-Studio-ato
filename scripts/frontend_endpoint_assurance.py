#!/usr/bin/env python3
"""Deterministic frontend -> endpoint assurance for Sovereign Studio ATO.

This scanner is a repository contract, not runtime truth. It inventories concrete
``/api/...`` references in the active browser frontend and proves that every
active internal reference has a matching server route in either the canonical
backend tree or the deployment-owned Flask application.

Important boundaries:
- no network access;
- no database access;
- no environment values are read;
- tests/specs/generated output are excluded from the frontend source inventory;
- explicit external/retired bridges are classified but never marked backend-backed;
- dynamic parameters are normalized to ``<p>`` so frontend/backend ownership can
  be compared deterministically.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / ".security-reports" / "frontend-endpoint-assurance.json"

SOURCE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx"})

# These are intentionally not claimed as routes of the canonical Flask backend.
# They remain visible in the report with a non-authoritative classification.
EXTERNAL_SERVICE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/api/sovereign-memory/", "external-memory-gateway"),
)
RETIRED_OR_NONCANONICAL_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/api/vps", "retired-vps-browser-bridge"),
    ("/api/ai/gemini", "retired-direct-gemini-bridge"),
)

# Exclude import fragments such as ./api/adminApiClient and nested URL fragments
# such as https://host/toolchain/api/v1. A real frontend endpoint begins at a
# path boundary, string/template boundary, or directly after an expression.
_FRONTEND_ENDPOINT_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])/api/[A-Za-z0-9_./${}()<>?&=:+%\-]+"
)
_DECORATOR_ROUTE_RE = re.compile(
    r"@(?P<decorator>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    r"\.(?P<kind>route|get|post|put|patch|delete)\(\s*[\"'](?P<route>[^\"']+)[\"']"
)
_ADD_URL_RULE_RE = re.compile(r"\.add_url_rule\(\s*[\"']([^\"']+)[\"']")
_BLUEPRINT_RE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*Blueprint\((?P<body>.*?)\)",
    re.DOTALL,
)
_BLUEPRINT_PREFIX_RE = re.compile(r"url_prefix\s*=\s*[\"']([^\"']+)[\"']")

_TEMPLATE_EXPR_RE = re.compile(r"\$\{[^{}]+\}")
_TEMPLATE_QUERY_SUFFIX_RE = re.compile(r"\$\{(?:suffix|query|queryString|params(?:\.toString\(\))?)\}$")
_FLASK_PARAM_RE = re.compile(r"<(?:(?:string|int|float|path|uuid|any\([^>]+\)):)?[^>]+>")
_COLON_PARAM_RE = re.compile(r"/:([A-Za-z_][A-Za-z0-9_]*)")
_MULTI_SLASH_RE = re.compile(r"/{2,}")


@dataclass(frozen=True)
class EndpointReference:
    endpoint: str
    normalized: str
    source: str
    line: int
    classification: str
    owner: str
    backed: bool
    backend_sources: tuple[str, ...]


@dataclass(frozen=True)
class BackendRoute:
    route: str
    normalized: str
    source: str
    line: int


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_frontend_production_file(path: Path) -> bool:
    rel = _relative(path)
    name = path.name.lower()
    if path.suffix.lower() not in SOURCE_SUFFIXES:
        return False
    if any(token in name for token in (".test.", ".spec.", ".e2e.")):
        return False
    if "/e2e/" in f"/{rel.lower()}/":
        return False
    if rel.startswith(("src/server/", "src/__tests__/")):
        return False
    return True


def frontend_source_files() -> list[Path]:
    src = ROOT / "src"
    return sorted(path for path in src.rglob("*") if path.is_file() and _is_frontend_production_file(path))


def backend_source_files() -> list[Path]:
    roots = (ROOT / "backend", ROOT / "scripts" / "sovereign-backend")
    found: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if not path.is_file():
                continue
            rel = _relative(path)
            if "/tests/" in f"/{rel}/" or path.name.startswith("test_"):
                continue
            found[rel] = path
    return [found[key] for key in sorted(found)]


def normalize_endpoint(raw: str) -> str:
    """Normalize frontend/backend dynamic route segments without retargeting paths."""
    value = str(raw or "").strip()
    if not value:
        return ""
    value = _TEMPLATE_QUERY_SUFFIX_RE.sub("", value)
    value = value.split("#", 1)[0].split("?", 1)[0]
    # Template expressions such as ${encodeURIComponent(jobId)} are one parameter.
    previous = None
    while previous != value:
        previous = value
        value = _TEMPLATE_EXPR_RE.sub("<p>", value)
    # A conservative fallback for endpoint fragments captured through nested calls.
    value = re.sub(r"\$\{[^}]+", "<p>", value)
    value = _FLASK_PARAM_RE.sub("<p>", value)
    value = _COLON_PARAM_RE.sub("/<p>", value)
    value = value.rstrip(".'\"`),;]} ")
    value = _MULTI_SLASH_RE.sub("/", value)
    if len(value) > 1:
        value = value.rstrip("/")
    return value


def _without_js_comments(source: str) -> str:
    """Mask JS/TS comments while preserving byte offsets and string literals."""
    chars = list(source)
    mode = "code"
    quote = ""
    escaped = False
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if mode == "line":
            if ch == "\n":
                mode = "code"
            else:
                chars[i] = " "
            i += 1
            continue
        if mode == "block":
            if ch == "*" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                mode = "code"
                i += 2
            else:
                if ch != "\n":
                    chars[i] = " "
                i += 1
            continue
        if mode == "string":
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                mode = "code"
                quote = ""
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            mode = "string"
            quote = ch
            i += 1
            continue
        if ch == "/" and nxt == "/":
            chars[i] = chars[i + 1] = " "
            mode = "line"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            chars[i] = chars[i + 1] = " "
            mode = "block"
            i += 2
            continue
        i += 1
    return "".join(chars)


def _line_for_offset(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def extract_backend_routes(paths: Iterable[Path] | None = None) -> list[BackendRoute]:
    routes: list[BackendRoute] = []
    for path in paths or backend_source_files():
        source = path.read_text("utf-8", errors="replace")
        blueprint_prefixes: dict[str, str] = {}
        for blueprint in _BLUEPRINT_RE.finditer(source):
            prefix = _BLUEPRINT_PREFIX_RE.search(blueprint.group("body"))
            if prefix:
                blueprint_prefixes[blueprint.group("name")] = prefix.group(1).rstrip("/")

        for match in _DECORATOR_ROUTE_RE.finditer(source):
            route = match.group("route")
            decorator_root = match.group("decorator").split(".", 1)[0]
            prefix = blueprint_prefixes.get(decorator_root, "")
            full_route = f"{prefix}{route}" if prefix else route
            if not full_route.startswith("/api/"):
                continue
            routes.append(
                BackendRoute(
                    route=full_route,
                    normalized=normalize_endpoint(full_route),
                    source=_relative(path),
                    line=_line_for_offset(source, match.start()),
                )
            )
        for match in _ADD_URL_RULE_RE.finditer(source):
            route = match.group(1)
            if not route.startswith("/api/"):
                continue
            routes.append(
                BackendRoute(
                    route=route,
                    normalized=normalize_endpoint(route),
                    source=_relative(path),
                    line=_line_for_offset(source, match.start()),
                )
            )
    return sorted(routes, key=lambda item: (item.normalized, item.source, item.line))


def _classification(endpoint: str, source: str) -> tuple[str, str]:
    for prefix, owner in EXTERNAL_SERVICE_PREFIXES:
        if endpoint == prefix.rstrip("/") or endpoint.startswith(prefix):
            return "EXTERNAL_SERVICE", owner
    for prefix, owner in RETIRED_OR_NONCANONICAL_PREFIXES:
        if endpoint == prefix or endpoint.startswith(prefix + "/"):
            return "RETIRED_OR_NONCANONICAL", owner
    if source == "src/features/ai/providerManager.ts":
        return "EXTERNAL_PROVIDER", "direct-third-party-provider-adapter"
    if source == "src/features/product/llm/adapters/ovhAnonymousAdapter.ts":
        return "EXTERNAL_PROVIDER", "ovh-anonymous-provider-adapter"
    return "ACTIVE_INTERNAL", "sovereign-backend"


def _backend_index(routes: Iterable[BackendRoute]) -> dict[str, tuple[str, ...]]:
    index: dict[str, set[str]] = {}
    for route in routes:
        index.setdefault(route.normalized, set()).add(route.source)
    return {key: tuple(sorted(values)) for key, values in sorted(index.items())}


def extract_frontend_endpoints(
    paths: Iterable[Path] | None = None,
    *,
    backend_routes: Iterable[BackendRoute] | None = None,
) -> list[EndpointReference]:
    routes = list(backend_routes) if backend_routes is not None else extract_backend_routes()
    index = _backend_index(routes)
    references: list[EndpointReference] = []
    for path in paths or frontend_source_files():
        source = path.read_text("utf-8", errors="replace")
        scan_source = _without_js_comments(source)
        source_name = _relative(path)
        for match in _FRONTEND_ENDPOINT_RE.finditer(scan_source):
            endpoint = match.group(0)
            normalized = normalize_endpoint(endpoint)
            if not normalized.startswith("/api/"):
                continue
            classification, owner = _classification(normalized, source_name)
            backend_sources = index.get(normalized, ())
            if classification == "ACTIVE_INTERNAL" and not backend_sources:
                prefix_sources = {
                    backend_source
                    for route, sources in index.items()
                    if route.startswith(normalized.rstrip("/") + "/")
                    for backend_source in sources
                }
                if prefix_sources:
                    classification = "ACTIVE_INTERNAL_PREFIX"
                    backend_sources = tuple(sorted(prefix_sources))
            backed = classification in {"ACTIVE_INTERNAL", "ACTIVE_INTERNAL_PREFIX"} and bool(backend_sources)
            references.append(
                EndpointReference(
                    endpoint=endpoint,
                    normalized=normalized,
                    source=source_name,
                    line=_line_for_offset(source, match.start()),
                    classification=classification,
                    owner=owner,
                    backed=backed,
                    backend_sources=backend_sources,
                )
            )
    # De-duplicate the same source-line-normalized reference while retaining provenance.
    unique: dict[tuple[str, int, str], EndpointReference] = {}
    for item in references:
        unique[(item.source, item.line, item.normalized)] = item
    return sorted(unique.values(), key=lambda item: (item.normalized, item.source, item.line))


def build_report() -> dict[str, object]:
    routes = extract_backend_routes()
    refs = extract_frontend_endpoints(backend_routes=routes)
    unbound = [item for item in refs if item.classification == "ACTIVE_INTERNAL" and not item.backed]
    active = [
        item for item in refs
        if item.classification in {"ACTIVE_INTERNAL", "ACTIVE_INTERNAL_PREFIX"}
    ]
    external = [
        item for item in refs
        if item.classification in {"EXTERNAL_SERVICE", "EXTERNAL_PROVIDER"}
    ]
    retired = [item for item in refs if item.classification == "RETIRED_OR_NONCANONICAL"]

    unique_active = {item.normalized for item in active}
    unique_unbound = {item.normalized for item in unbound}
    unique_backend = {item.normalized for item in routes}

    return {
        "schemaVersion": "sovereign.frontend-endpoint-assurance.v1",
        "status": "PASS" if not unbound else "FAIL",
        "truthClass": "STATIC_CONTRACT_EVIDENCE",
        "authoritativeRuntime": False,
        "runtimeConnectivityProven": False,
        "scope": {
            "frontend": "src/**/*.{ts,tsx,js,jsx} excluding tests/specs/src-server",
            "backend": ["backend/**/*.py", "scripts/sovereign-backend/**/*.py"],
        },
        "counts": {
            "frontendSourceFiles": len(frontend_source_files()),
            "backendSourceFiles": len(backend_source_files()),
            "backendRoutes": len(routes),
            "uniqueBackendRoutes": len(unique_backend),
            "frontendReferences": len(refs),
            "uniqueActiveInternalEndpoints": len(unique_active),
            "uniqueUnboundActiveInternalEndpoints": len(unique_unbound),
            "externalServiceReferences": len(external),
            "retiredOrNoncanonicalReferences": len(retired),
        },
        "unbound": [asdict(item) for item in unbound],
        "references": [asdict(item) for item in refs],
        "backendRoutes": [asdict(item) for item in routes],
        "truthNotice": (
            "Route ownership is static repository evidence only. A passing report does not prove "
            "authentication, deployment, runtime health, target effects or endpoint semantics."
        ),
    }


def write_report(report: dict[str, object], destination: Path = REPORT_PATH) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(REPORT_PATH), help="report destination")
    parser.add_argument("--no-write", action="store_true", help="do not write a report artifact")
    args = parser.parse_args(argv)

    report = build_report()
    if not args.no_write:
        write_report(report, Path(args.report))
    print(json.dumps({
        "schemaVersion": report["schemaVersion"],
        "status": report["status"],
        "counts": report["counts"],
        "unbound": report["unbound"],
        "truthNotice": report["truthNotice"],
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
