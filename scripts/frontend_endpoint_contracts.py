#!/usr/bin/env python3
"""Deterministic frontend-to-endpoint contract compiler for Sovereign Studio ATO.

This scanner is repository evidence, not runtime truth.  It binds production
frontend request expressions to statically registered backend routes, preserves
explicit non-active endpoint surfaces, inventories test references, and writes a
bounded machine-readable report for Pytest, CI and Playwright.

It never performs a network request, reads credentials, or mutates product state.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
from typing import Iterable, Iterator, Sequence
from urllib.parse import urlsplit

SCHEMA_VERSION = "sovereign.frontend-endpoint-contracts.v1"
DEFAULT_REPORT = ".security-reports/sovereign-frontend-endpoints.json"

_SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
_BACKEND_SUFFIXES = _SOURCE_SUFFIXES | {".py"}
_SKIP_PARTS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "playwright-report",
    "test-results",
    "__pycache__",
}
_TEST_MARKERS = ("/tests/", "/test/", "__tests__", ".test.", ".spec.", "/e2e/")
_FRONTEND_PREFIXES = ("src/", "ato-v2/", "apps/", "packages/", "sovereign-studio-rn/")
_BACKEND_PREFIXES = (
    "backend/",
    "scripts/sovereign-backend/",
    "src/server/",
    "server/",
    "launch-bot-v1/server/",
    "cloudflare-worker/",
    "cloudflare-worker-ai-proxy/",
)
_NON_ACTIVE_SURFACES = {
    "legacy-unreferenced",
    "disabled-launcher",
    "test-only",
    "quarantined",
    "retired",
}
_SURFACE_MARKER = re.compile(r"sovereign-endpoint-surface:\s*([a-z0-9-]+)", re.I)
_CALL_HEAD = re.compile(r"(?<![A-Za-z0-9_$])([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(")
_CONST_ASSIGNMENT = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(.{1,1200}?);",
    re.S,
)
_METHOD_OPTION = re.compile(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]", re.I)
_EXPRESS_ROUTE = re.compile(
    r"\b(?:app|router|server)\.(get|post|put|patch|delete|options|head)\(\s*"
    r"(['\"`])(/[^'\"`]+)\2",
    re.I,
)
_ENDPOINT_PREFIXES = ("/api/", "/a2a/", "/.well-known/", "/generated/")
_FIRST_PARTY_ABSOLUTE_HOSTS = {
    "sovereign-backend.arelorian.de",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}
_HTTPISH_NAMES = {
    "fetch",
    "request",
    "requestjson",
    "requestobject",
    "requestsnapshot",
    "requestjanitortool",
    "apirequest",
    "apifetch",
    "authfetch",
    "fetchjson",
    "callapi",
    "postjson",
    "getjson",
    "putjson",
    "patchjson",
    "deletejson",
}
_METHOD_NAMES = {"get", "post", "put", "patch", "delete", "options", "head"}
_CALL_METHOD_DEFAULTS = {
    "callopenaicompatible": "POST",
}
_STATIC_IMPORT = re.compile(
    r"\b(?P<kind>import|export)\s+(?P<body>[\s\S]{1,2000}?)\s+from\s+"
    r"(?P<quote>['\"])(?P<specifier>[^'\"]+)(?P=quote)",
)
_SIDE_EFFECT_IMPORT = re.compile(r"\bimport\s+(?P<quote>['\"])(?P<specifier>[^'\"]+)(?P=quote)")
_DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(\s*(?P<quote>['\"])(?P<specifier>[^'\"]+)(?P=quote)\s*\)")
_LEGACY_IMPORT_STATUSES = frozenset({"legacy-unreferenced", "retired", "quarantined"})


@dataclass(frozen=True)
class StringLiteral:
    value: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class FrontendCall:
    path: str
    method: str
    file: str
    line: int
    call_name: str
    source_kind: str
    surface_status: str
    active_surface: bool


@dataclass(frozen=True)
class ExternalCall:
    url: str
    host: str
    path: str
    method: str
    file: str
    line: int
    call_name: str
    surface_status: str
    active_surface: bool


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    source_status: str
    target_status: str
    line: int
    dynamic: bool


@dataclass(frozen=True)
class BackendRoute:
    path: str
    methods: tuple[str, ...]
    file: str
    line: int
    source_kind: str


@dataclass(frozen=True)
class Binding:
    call: FrontendCall
    status: str
    backend_routes: tuple[BackendRoute, ...]
    unit_test_refs: tuple[str, ...]
    backend_test_refs: tuple[str, ...]
    e2e_test_refs: tuple[str, ...]


def _posix(path: Path) -> str:
    return path.as_posix()


def _is_test_path(relative: str) -> bool:
    normalized = f"/{relative.casefold()}"
    return any(marker in normalized for marker in _TEST_MARKERS)


def _is_skipped(path: Path) -> bool:
    return any(part in _SKIP_PARTS for part in path.parts)


def _walk(repo: Path, prefixes: Sequence[str], suffixes: set[str]) -> list[str]:
    output: list[str] = []
    for prefix in prefixes:
        root = repo / prefix
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file() or _is_skipped(path) or path.suffix.casefold() not in suffixes:
                continue
            relative = _posix(path.relative_to(repo))
            output.append(relative)
    return sorted(set(output))


def _safe_text(path: Path, maximum: int = 2_000_000) -> str:
    try:
        if path.stat().st_size > maximum:
            return ""
        return path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _surface(text: str) -> tuple[str, bool]:
    header = "\n".join(text.splitlines()[:20])
    match = _SURFACE_MARKER.search(header)
    status = match.group(1).casefold() if match else "active"
    return status, status not in _NON_ACTIVE_SURFACES


def _surface_for(relative: str, text: str) -> tuple[str, bool]:
    if relative.startswith("sovereign-studio-rn/"):
        return "legacy-unreferenced", False
    return _surface(text)


def _frontend_surface_map(repo: Path) -> dict[str, tuple[str, bool]]:
    output: dict[str, tuple[str, bool]] = {}
    for relative in _walk(repo, _FRONTEND_PREFIXES, _SOURCE_SUFFIXES):
        if _is_test_path(relative) or relative.startswith("src/server/"):
            continue
        text = _safe_text(repo / relative)
        if text:
            output[relative] = _surface_for(relative, text)
    return output


def _is_type_only_import(kind: str, body: str) -> bool:
    normalized = " ".join(body.split()).strip()
    if normalized.startswith("type "):
        return True
    brace_match = re.fullmatch(r"\{([\s\S]*)\}", body.strip())
    if brace_match:
        items = [item.strip() for item in brace_match.group(1).split(",") if item.strip()]
        return bool(items) and all(item.startswith("type ") for item in items)
    return kind == "export" and normalized.startswith("type ")


def _import_specifiers(text: str) -> list[tuple[str, int, bool]]:
    output: list[tuple[str, int, bool]] = []
    seen: set[tuple[str, int, bool]] = set()
    for match in _STATIC_IMPORT.finditer(text):
        if _is_type_only_import(match.group("kind"), match.group("body")):
            continue
        item = (match.group("specifier"), _line(text, match.start()), False)
        if item not in seen:
            seen.add(item)
            output.append(item)
    for pattern, dynamic in ((_SIDE_EFFECT_IMPORT, False), (_DYNAMIC_IMPORT, True)):
        for match in pattern.finditer(text):
            item = (match.group("specifier"), _line(text, match.start()), dynamic)
            if item not in seen:
                seen.add(item)
                output.append(item)
    return output


def _resolve_frontend_import(source: str, specifier: str, known_files: set[str]) -> str:
    if specifier.startswith("@/"):
        base = posixpath.normpath(posixpath.join("src", specifier[2:]))
    elif specifier.startswith("@ato-v2/"):
        base = posixpath.normpath(posixpath.join("src/ato-v2", specifier[len("@ato-v2/"):]))
    elif specifier.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(source), specifier))
    else:
        return ""
    if base == ".." or base.startswith("../") or base.startswith("/"):
        return ""
    candidates: list[str] = [base]
    suffix = Path(base).suffix.casefold()
    if not suffix:
        candidates.extend(f"{base}{extension}" for extension in sorted(_SOURCE_SUFFIXES))
        candidates.extend(f"{base}/index{extension}" for extension in sorted(_SOURCE_SUFFIXES))
    elif suffix in {".js", ".jsx"}:
        stem = base[: -len(suffix)]
        candidates.extend(f"{stem}{extension}" for extension in (".ts", ".tsx"))
    return next((candidate for candidate in candidates if candidate in known_files), "")


def _frontend_import_edges(
    repo: Path,
    surfaces: dict[str, tuple[str, bool]],
) -> list[ImportEdge]:
    known_files = set(surfaces)
    output: list[ImportEdge] = []
    seen: set[tuple[str, str, int, bool]] = set()
    for source in sorted(surfaces):
        text = _safe_text(repo / source)
        if not text:
            continue
        for specifier, line, dynamic in _import_specifiers(text):
            target = _resolve_frontend_import(source, specifier, known_files)
            if not target:
                continue
            key = (source, target, line, dynamic)
            if key in seen:
                continue
            seen.add(key)
            output.append(ImportEdge(
                source=source,
                target=target,
                source_status=surfaces[source][0],
                target_status=surfaces[target][0],
                line=line,
                dynamic=dynamic,
            ))
    return sorted(output, key=lambda item: (item.source, item.target, item.line, item.dynamic))


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _iter_js_strings(text: str, start_offset: int = 0) -> Iterator[StringLiteral]:
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "/" and i + 1 < length and text[i + 1] == "/":
            newline = text.find("\n", i + 2)
            i = length if newline < 0 else newline + 1
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = length if end < 0 else end + 2
            continue
        if char not in {"'", '"', "`"}:
            i += 1
            continue
        quote = char
        literal_start = i
        i += 1
        buffer: list[str] = []
        while i < length:
            current = text[i]
            if current == "\\":
                if i + 1 < length:
                    buffer.append(current)
                    buffer.append(text[i + 1])
                    i += 2
                    continue
                buffer.append(current)
                i += 1
                continue
            if current == quote:
                yield StringLiteral(
                    value="".join(buffer),
                    start=start_offset + literal_start,
                    end=start_offset + i + 1,
                    quote=quote,
                )
                i += 1
                break
            buffer.append(current)
            i += 1
        else:
            return


def _matching_parenthesis(text: str, open_index: int) -> int | None:
    depth = 0
    i = open_index
    length = len(text)
    while i < length:
        char = text[i]
        if char == "/" and i + 1 < length and text[i + 1] == "/":
            newline = text.find("\n", i + 2)
            i = length if newline < 0 else newline + 1
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = length if end < 0 else end + 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            i += 1
            while i < length:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _split_top_level_arguments(value: str) -> list[str]:
    args: list[str] = []
    start = 0
    depth_round = 0
    depth_square = 0
    depth_curly = 0
    i = 0
    while i < len(value):
        char = value[i]
        if char in {"'", '"', "`"}:
            quote = char
            i += 1
            while i < len(value):
                if value[i] == "\\":
                    i += 2
                    continue
                if value[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if char == "/" and i + 1 < len(value) and value[i + 1] == "/":
            newline = value.find("\n", i + 2)
            i = len(value) if newline < 0 else newline + 1
            continue
        if char == "/" and i + 1 < len(value) and value[i + 1] == "*":
            end = value.find("*/", i + 2)
            i = len(value) if end < 0 else end + 2
            continue
        if char == "(":
            depth_round += 1
        elif char == ")":
            depth_round = max(0, depth_round - 1)
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square = max(0, depth_square - 1)
        elif char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly = max(0, depth_curly - 1)
        elif char == "," and depth_round == depth_square == depth_curly == 0:
            args.append(value[start:i].strip())
            start = i + 1
        i += 1
    tail = value[start:].strip()
    if tail or value.strip():
        args.append(tail)
    return args


def _normalize_path(value: str) -> str:
    selected = str(value or "").strip()
    if not selected:
        return ""
    prefix_indexes = [selected.find(prefix) for prefix in _ENDPOINT_PREFIXES if selected.find(prefix) >= 0]
    if not prefix_indexes:
        return ""
    selected = selected[min(prefix_indexes):]
    selected = selected.split("?", 1)[0].split("#", 1)[0]
    selected = re.sub(r"\$\{[^}]+\}", "<p>", selected)
    selected = re.sub(r"<[^>]+>", "<p>", selected)
    selected = re.sub(r"\{[^{}\/]+\}", "<p>", selected)
    selected = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", "<p>", selected)
    selected = re.sub(r"/+", "/", selected)
    return selected.rstrip("/") or "/"


def _concatenated_route(argument: str) -> str:
    if "+" not in argument:
        return ""
    literals = list(_iter_js_strings(argument))
    start_index = next(
        (
            index
            for index, literal in enumerate(literals)
            if any(prefix in literal.value for prefix in _ENDPOINT_PREFIXES)
        ),
        -1,
    )
    if start_index < 0:
        return ""
    selected = literals[start_index:]
    first = selected[0]
    if _is_external_absolute_url(first.value):
        return ""
    value = first.value
    previous = first
    for literal in selected[1:]:
        between = argument[previous.end:literal.start]
        residue = re.sub(r"[+\s]", "", between)
        if residue:
            value += "<p>"
        value += literal.value
        previous = literal
    tail = argument[previous.end:]
    if re.sub(r"[+\s,)]", "", tail):
        value += "<p>"
    return _normalize_path(value)


def _is_external_absolute_url(value: str) -> bool:
    candidate = str(value or "").strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", candidate):
        return False
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return True
    hostname = str(parsed.hostname or "").casefold()
    return bool(hostname and hostname not in _FIRST_PARTY_ABSOLUTE_HOSTS)


def _route_literals(expression: str, constants: dict[str, str]) -> list[str]:
    selected = expression.strip()
    if re.fullmatch(r"[A-Za-z_$][\w$]*", selected) and selected in constants:
        selected = constants[selected]
    routes: list[str] = []
    strings = list(_iter_js_strings(selected))
    for argument in _split_top_level_arguments(selected):
        concatenated = _concatenated_route(argument)
        if concatenated:
            routes.append(concatenated)
            continue
        for literal in _iter_js_strings(argument):
            if _is_external_absolute_url(literal.value):
                continue
            normalized = _normalize_path(literal.value)
            if normalized:
                routes.append(normalized)

    # Central Agent client helper: jobPath(jobId, '/suffix') expands to the
    # canonical owned-job route family. This is source parsing only; it grants
    # no endpoint reachability or authorization claim.
    if "jobPath" in selected:
        suffixes = [literal.value.split("?", 1)[0] for literal in strings if literal.value.startswith("/")]
        for suffix in suffixes:
            if suffix.startswith(_ENDPOINT_PREFIXES):
                continue
            routes.append(_normalize_path(f"/api/user/agent/jobs/<p>{suffix}"))

    return sorted({route for route in routes if route})


def _constant_expressions(text: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in _CONST_ASSIGNMENT.finditer(text)}


def _is_httpish(call_name: str) -> bool:
    last = call_name.rsplit(".", 1)[-1].casefold()
    if last in _HTTPISH_NAMES or last in _METHOD_NAMES or last in _CALL_METHOD_DEFAULTS:
        return True
    return (
        last.startswith("fetch")
        or last.endswith(("fetch", "request"))
        or last in {"query", "mutation"}
    )


def _method_for(call_name: str, arguments: str) -> str:
    last = call_name.rsplit(".", 1)[-1].casefold()
    if last in _METHOD_NAMES:
        return last.upper()
    explicit = _METHOD_OPTION.search(arguments)
    if explicit:
        return explicit.group(1).upper()
    for method in ("delete", "patch", "post", "put", "get"):
        if last.startswith(method):
            return method.upper()
    if last in _CALL_METHOD_DEFAULTS:
        return _CALL_METHOD_DEFAULTS[last]
    if last == "fetch" or last.startswith("fetch") or last.endswith(("fetch", "request")):
        return "GET"
    return "UNKNOWN"


def _frontend_calls(repo: Path) -> list[FrontendCall]:
    files = _walk(repo, _FRONTEND_PREFIXES, _SOURCE_SUFFIXES)
    output: list[FrontendCall] = []
    seen: set[tuple[str, str, str, int, str]] = set()
    for relative in files:
        if _is_test_path(relative) or relative.startswith("src/server/"):
            continue
        text = _safe_text(repo / relative)
        if not text:
            continue
        surface_status, active_surface = _surface_for(relative, text)
        constants = _constant_expressions(text)
        request_literal_ranges: list[tuple[int, int]] = []
        for match in _CALL_HEAD.finditer(text):
            open_index = text.find("(", match.start(), match.end())
            if open_index < 0:
                continue
            close_index = _matching_parenthesis(text, open_index)
            if close_index is None:
                continue
            call_name = match.group(1)
            arguments = text[open_index + 1:close_index]
            routes = _route_literals(arguments, constants)
            if not routes:
                continue
            requestlike = _is_httpish(call_name)
            method = _method_for(call_name, arguments) if requestlike else "UNKNOWN"
            source_kind = "request-call" if requestlike else "route-call"
            line = _line(text, match.start())
            for route in routes:
                key = (route, method, relative, line, source_kind)
                if key in seen:
                    continue
                seen.add(key)
                output.append(FrontendCall(
                    path=route,
                    method=method,
                    file=relative,
                    line=line,
                    call_name=call_name,
                    source_kind=source_kind,
                    surface_status=surface_status,
                    active_surface=active_surface,
                ))
            request_literal_ranges.append((open_index, close_index))

        # Route constants and literals remain inventory evidence even when a
        # dynamic helper prevents static call attribution. They do not fail the
        # active request gate by themselves.
        for literal in _iter_js_strings(text):
            if any(start <= literal.start <= end for start, end in request_literal_ranges):
                continue
            route = _normalize_path(literal.value)
            if not route:
                continue
            key = (route, "UNKNOWN", relative, _line(text, literal.start), "route-literal")
            if key in seen:
                continue
            seen.add(key)
            output.append(FrontendCall(
                path=route,
                method="UNKNOWN",
                file=relative,
                line=_line(text, literal.start),
                call_name="literal",
                source_kind="route-literal",
                surface_status=surface_status,
                active_surface=active_surface,
            ))
    return sorted(output, key=lambda item: (item.path, item.method, item.file, item.line, item.source_kind))


def _external_path(value: str) -> tuple[str, str, str]:
    parsed = urlsplit(str(value or "").strip())
    host = str(parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError:
        port = None
    authority = f"{host}:{port}" if port is not None else host
    raw_path = parsed.path or "/"
    normalized_path = re.sub(r"\$\{[^}]+\}", "<p>", raw_path)
    normalized_path = re.sub(r"/+", "/", normalized_path)
    normalized_url = f"{parsed.scheme.casefold()}://{authority}{normalized_path}"
    return normalized_url, host, normalized_path


def _external_frontend_calls(repo: Path) -> list[ExternalCall]:
    output: list[ExternalCall] = []
    seen: set[tuple[str, str, str, int, str]] = set()
    for relative in _walk(repo, _FRONTEND_PREFIXES, _SOURCE_SUFFIXES):
        if _is_test_path(relative) or relative.startswith("src/server/"):
            continue
        text = _safe_text(repo / relative)
        if not text:
            continue
        surface_status, active_surface = _surface_for(relative, text)
        for match in _CALL_HEAD.finditer(text):
            open_index = text.find("(", match.start(), match.end())
            if open_index < 0:
                continue
            close_index = _matching_parenthesis(text, open_index)
            if close_index is None:
                continue
            call_name = match.group(1)
            if not _is_httpish(call_name):
                continue
            arguments = text[open_index + 1:close_index]
            method = _method_for(call_name, arguments)
            for literal in _iter_js_strings(arguments):
                if not _is_external_absolute_url(literal.value):
                    continue
                url, host, external_path = _external_path(literal.value)
                key = (url, method, relative, _line(text, match.start()), call_name)
                if key in seen:
                    continue
                seen.add(key)
                output.append(ExternalCall(
                    url=url,
                    host=host,
                    path=external_path,
                    method=method,
                    file=relative,
                    line=_line(text, match.start()),
                    call_name=call_name,
                    surface_status=surface_status,
                    active_surface=active_surface,
                ))
    return sorted(output, key=lambda item: (item.host, item.path, item.method, item.file, item.line))


def _attribute_name(value: ast.AST) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        prefix = _attribute_name(value.value)
        return f"{prefix}.{value.attr}" if prefix else value.attr
    return ""


def _constant_string(value: ast.AST | None) -> str:
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ""


def _blueprint_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in tree.body:
        target_name = ""
        call: ast.Call | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
            target_name = node.targets[0].id
            call = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and isinstance(node.value, ast.Call):
            target_name = node.target.id
            call = node.value
        if not target_name or call is None or _attribute_name(call.func).rsplit(".", 1)[-1] != "Blueprint":
            continue
        for keyword in call.keywords:
            if keyword.arg == "url_prefix":
                prefix = _constant_string(keyword.value)
                if prefix:
                    prefixes[target_name] = prefix
    return prefixes


def _python_backend_routes(relative: str, text: str) -> list[BackendRoute]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    prefixes = _blueprint_prefixes(tree)
    output: list[BackendRoute] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            decorated = _attribute_name(decorator.func)
            if "." not in decorated:
                continue
            owner, kind = decorated.rsplit(".", 1)
            normalized_kind = kind.casefold()
            if normalized_kind not in {"route", "api_route", "get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            raw_path = _constant_string(decorator.args[0] if decorator.args else None)
            if not raw_path.startswith("/"):
                continue
            owner_root = owner.split(".", 1)[0]
            prefix = prefixes.get(owner_root, "")
            full_path = f"{prefix.rstrip('/')}{raw_path}" if prefix and not raw_path.startswith(prefix.rstrip("/") + "/") else raw_path
            path = _normalize_path(full_path)
            if not path:
                continue
            if normalized_kind in _METHOD_NAMES:
                methods = (normalized_kind.upper(),)
            else:
                methods_value: ast.AST | None = None
                for keyword in decorator.keywords:
                    if keyword.arg == "methods":
                        methods_value = keyword.value
                        break
                selected: list[str] = []
                if isinstance(methods_value, (ast.List, ast.Tuple, ast.Set)):
                    selected = [
                        _constant_string(item).upper()
                        for item in methods_value.elts
                        if _constant_string(item)
                    ]
                methods = tuple(sorted(set(selected))) or ("GET",)
            output.append(BackendRoute(
                path=path,
                methods=methods,
                file=relative,
                line=int(getattr(decorator, "lineno", node.lineno)),
                source_kind="python-route",
            ))
    return output


def _backend_routes(repo: Path) -> list[BackendRoute]:
    files = _walk(repo, _BACKEND_PREFIXES, _BACKEND_SUFFIXES)
    output: list[BackendRoute] = []
    seen: set[tuple[str, tuple[str, ...], str, int]] = set()
    for relative in files:
        if _is_test_path(relative) or relative == "backend/app.py":
            continue
        text = _safe_text(repo / relative)
        if not text:
            continue
        status, active = _surface(text)
        if not active or status in _NON_ACTIVE_SURFACES:
            continue
        if relative.endswith(".py"):
            candidates = _python_backend_routes(relative, text)
        else:
            candidates = []
            for match in _EXPRESS_ROUTE.finditer(text):
                path = _normalize_path(match.group(3))
                if path:
                    candidates.append(BackendRoute(
                        path=path,
                        methods=(match.group(1).upper(),),
                        file=relative,
                        line=_line(text, match.start()),
                        source_kind="javascript-route",
                    ))
        for route in candidates:
            key = (route.path, route.methods, route.file, route.line)
            if key in seen:
                continue
            seen.add(key)
            output.append(route)
    return sorted(output, key=lambda item: (item.path, item.methods, item.file, item.line))


def _path_regex(path: str) -> re.Pattern[str]:
    escaped = re.escape(path).replace(re.escape("<p>"), r"[^/]+")
    return re.compile(rf"^{escaped}$")


def _paths_match(left: str, right: str) -> bool:
    return bool(_path_regex(left).fullmatch(right) or _path_regex(right).fullmatch(left))


def _test_files(repo: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for path in repo.rglob("*"):
        if not path.is_file() or _is_skipped(path):
            continue
        relative = _posix(path.relative_to(repo))
        if not _is_test_path(relative) or path.suffix.casefold() not in (_SOURCE_SUFFIXES | {".py"}):
            continue
        text = _safe_text(path)
        if text:
            output[relative] = text
    return output


def _test_references(path: str, tests: dict[str, str]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    static_prefix = path.split("<p>", 1)[0].rstrip("/")
    if len(static_prefix) < 5:
        return (), (), ()
    unit: list[str] = []
    backend: list[str] = []
    e2e: list[str] = []
    for relative, text in tests.items():
        if static_prefix not in text:
            continue
        lowered = relative.casefold()
        if "/e2e/" in f"/{lowered}" or ".spec." in lowered:
            e2e.append(relative)
        elif relative.endswith(".py"):
            backend.append(relative)
        else:
            unit.append(relative)
    return tuple(sorted(unit)[:40]), tuple(sorted(backend)[:40]), tuple(sorted(e2e)[:40])


def _bind(calls: Sequence[FrontendCall], routes: Sequence[BackendRoute], tests: dict[str, str]) -> list[Binding]:
    bindings: list[Binding] = []
    for call in calls:
        path_matches = tuple(route for route in routes if _paths_match(call.path, route.path))
        methods = {method for route in path_matches for method in route.methods}
        if call.path.startswith("/generated/"):
            status = "STATIC_ASSET"
        elif not call.active_surface:
            status = "NON_ACTIVE"
        elif call.source_kind == "route-literal":
            status = "LITERAL_BOUND" if path_matches else "LITERAL_ONLY"
        elif not path_matches:
            status = "UNMATCHED"
        elif call.method == "UNKNOWN":
            status = "PATH_BOUND_METHOD_UNKNOWN"
        elif call.method not in methods:
            status = "METHOD_MISMATCH"
        else:
            status = "BOUND"
        unit, backend, e2e = _test_references(call.path, tests)
        bindings.append(Binding(
            call=call,
            status=status,
            backend_routes=path_matches,
            unit_test_refs=unit,
            backend_test_refs=backend,
            e2e_test_refs=e2e,
        ))
    return bindings


def _tree_hash(repo: Path, files: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(set(files)):
        payload = (repo / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def _git_revision(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        revision = result.stdout.strip().lower()
        return revision if re.fullmatch(r"[0-9a-f]{40}", revision) else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def build_report(repo: Path) -> dict[str, object]:
    repo = repo.resolve()
    surfaces = _frontend_surface_map(repo)
    import_edges = _frontend_import_edges(repo, surfaces)
    calls = _frontend_calls(repo)
    external_calls = _external_frontend_calls(repo)
    routes = _backend_routes(repo)
    tests = _test_files(repo)
    bindings = _bind(calls, routes, tests)

    active_requests = [
        item for item in bindings
        if item.call.active_surface and item.call.source_kind == "request-call" and not item.call.path.startswith("/generated/")
    ]
    unmatched = [item for item in active_requests if item.status == "UNMATCHED"]
    mismatches = [item for item in active_requests if item.status == "METHOD_MISMATCH"]
    unknown_methods = [item for item in active_requests if item.status == "PATH_BOUND_METHOD_UNKNOWN"]
    bound = [item for item in active_requests if item.status == "BOUND"]
    active_mutations = [
        item for item in bound
        if item.call.method in {"POST", "PUT", "PATCH", "DELETE"}
    ]
    active_reads = [
        item for item in bound
        if item.call.method in {"GET", "HEAD", "OPTIONS"}
    ]

    def has_test_reference(item: Binding) -> bool:
        return bool(item.unit_test_refs or item.backend_test_refs or item.e2e_test_refs)

    untested_mutations = [item for item in active_mutations if not has_test_reference(item)]
    untested_reads = [item for item in active_reads if not has_test_reference(item)]
    active_external_calls = [item for item in external_calls if item.active_surface]
    external_unknown_methods = [item for item in active_external_calls if item.method == "UNKNOWN"]
    legacy_import_violations = [
        edge
        for edge in import_edges
        if surfaces.get(edge.source, ("active", True))[1]
        and edge.target_status in _LEGACY_IMPORT_STATUSES
    ]

    errors = [
        {
            "family": "FRONTEND_ENDPOINT_UNMATCHED",
            "method": item.call.method,
            "path": item.call.path,
            "file": item.call.file,
            "line": item.call.line,
        }
        for item in unmatched
    ] + [
        {
            "family": "FRONTEND_ENDPOINT_METHOD_MISMATCH",
            "method": item.call.method,
            "path": item.call.path,
            "file": item.call.file,
            "line": item.call.line,
            "backendMethods": sorted({method for route in item.backend_routes for method in route.methods}),
        }
        for item in mismatches
    ]
    errors.extend(
        {
            "family": "ACTIVE_IMPORTS_NON_ACTIVE_ENDPOINT_SURFACE",
            "source": edge.source,
            "target": edge.target,
            "sourceStatus": edge.source_status,
            "targetStatus": edge.target_status,
            "line": edge.line,
            "dynamic": edge.dynamic,
        }
        for edge in legacy_import_violations
    )
    errors.extend(
        {
            "family": "FRONTEND_MUTATION_TEST_EVIDENCE_MISSING",
            "method": item.call.method,
            "path": item.call.path,
            "file": item.call.file,
            "line": item.call.line,
        }
        for item in untested_mutations
    )
    errors.extend(
        {
            "family": "EXTERNAL_ENDPOINT_METHOD_UNKNOWN",
            "url": item.url,
            "host": item.host,
            "file": item.file,
            "line": item.line,
            "callName": item.call_name,
        }
        for item in external_unknown_methods
    )

    warnings = [
        {
            "family": "FRONTEND_READ_TEST_EVIDENCE_MISSING",
            "method": item.call.method,
            "path": item.call.path,
            "file": item.call.file,
            "line": item.call.line,
        }
        for item in untested_reads
    ] + [
        {
            "family": "FRONTEND_ENDPOINT_METHOD_UNKNOWN",
            "path": item.call.path,
            "file": item.call.file,
            "line": item.call.line,
            "callName": item.call.call_name,
        }
        for item in unknown_methods
    ]

    relevant_files = list(surfaces) + [call.file for call in calls] + [call.file for call in external_calls] + [route.file for route in routes] + list(tests)
    canonical = {
        "schemaVersion": SCHEMA_VERSION,
        "revision": _git_revision(repo),
        "sourceTreeSha256": _tree_hash(repo, relevant_files),
        "summary": {
            "frontendModuleCount": len(surfaces),
            "importEdgeCount": len(import_edges),
            "legacyImportViolationCount": len(legacy_import_violations),
            "frontendCallCount": len(calls),
            "activeRequestCount": len(active_requests),
            "boundActiveRequestCount": len(bound),
            "unmatchedActiveRequestCount": len(unmatched),
            "methodMismatchCount": len(mismatches),
            "methodUnknownCount": len(unknown_methods),
            "activeMutationRequestCount": len(active_mutations),
            "activeMutationWithoutTestEvidenceCount": len(untested_mutations),
            "activeReadRequestCount": len(active_reads),
            "activeReadWithoutTestEvidenceCount": len(untested_reads),
            "backendRouteCount": len(routes),
            "externalRequestCount": len(external_calls),
            "activeExternalRequestCount": len(active_external_calls),
            "externalMethodUnknownCount": len(external_unknown_methods),
            "testFileCount": len(tests),
        },
        "importEdges": [asdict(edge) for edge in import_edges],
        "bindings": [
            {
                "call": asdict(item.call),
                "status": item.status,
                "backendRoutes": [asdict(route) for route in item.backend_routes],
                "testReferences": {
                    "unit": list(item.unit_test_refs),
                    "backend": list(item.backend_test_refs),
                    "e2e": list(item.e2e_test_refs),
                },
            }
            for item in bindings
        ],
        "backendRoutes": [asdict(route) for route in routes],
        "externalCalls": [asdict(call) for call in external_calls],
        "errors": errors,
        "warnings": warnings,
        "truthBoundary": {
            "repositoryContractEvidence": True,
            "networkRequestsPerformed": False,
            "runtimeReachabilityProven": False,
            "authenticationProven": False,
            "targetEffectProven": False,
            "externalTargetReachabilityProven": False,
        },
    }
    canonical["reportSha256"] = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    canonical["status"] = "pass" if not errors else "fail"
    return canonical


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="JSON report path relative to repository root")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on active unmatched or method-mismatched calls")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(list(argv if argv is not None else sys.argv[1:]))
    repo = Path(args.repo).resolve()
    report = build_report(repo)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = repo / report_path
    report_path = report_path.resolve()
    if report_path != repo and repo not in report_path.parents:
        print(json.dumps({
            "schemaVersion": SCHEMA_VERSION,
            "status": "invalid-report-path",
            "repository": _posix(repo),
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    write_report(report, report_path)
    print(json.dumps({
        "schemaVersion": report["schemaVersion"],
        "status": report["status"],
        "revision": report["revision"],
        "reportSha256": report["reportSha256"],
        "summary": report["summary"],
        "reportPath": _posix(report_path),
        "runtimeReachabilityProven": False,
    }, ensure_ascii=False, sort_keys=True))
    return 1 if args.check and report["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
