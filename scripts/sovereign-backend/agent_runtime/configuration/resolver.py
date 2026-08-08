"""Configuration Provenance - deterministic resolver.

Mirrors ``src/runtime/config/sovereignConfigResolver.ts``. Resolves an ordered
set of sources into a redacted projection with a byte-identical receipt hash.
Unknown sources and bare remote URLs fail closed. Remote config requires
pre-bound origin, digest and signature/hash. Drift against an expected binding
invalidates the resolution (CONTRADICTED) so prior run/permission bindings and
active action plans are blocked rather than silently continuing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .config_canonicalize import hash_value, merge_values, schema_hash_from_fields
from .config_sources import (
    ConfigDriftRecord,
    ConfigResolutionContract,
    ConfigSourceContract,
    ConfigSourceKind,
    SOURCE_ORDER,
    SOURCE_PRIORITY,
    SourceHashRecord,
    is_allowed_source_kind,
    default_priority_for,
)


@dataclass(frozen=True)
class ResolveOptions:
    expected_receipt_hash: Optional[str] = None
    allowed_remote_origins: frozenset[str] = frozenset()
    schema_fields: Optional[list[dict[str, str]]] = None


def resolve_config_sources(
    sources: list[ConfigSourceContract],
    options: Optional[ResolveOptions] = None,
) -> ConfigResolutionContract:
    options = options or ResolveOptions()
    errors: list[str] = []
    allowed_origins = options.allowed_remote_origins or frozenset()

    validated: list[ConfigSourceContract] = []
    for source in sources:
        if not is_allowed_source_kind(source.kind):
            errors.append(f"unknown source kind: {source.kind} (id={source.id})")
            continue
        if not source.revision:
            errors.append(f"missing revision (id={source.id})")
            continue
        if not source.content_hash:
            errors.append(f"missing contentHash (id={source.id})")
            continue
        if not source.schema_hash:
            errors.append(f"missing schemaHash (id={source.id})")
            continue
        if source.remote is not None:
            if not source.remote.origin:
                errors.append(f"remote source without origin (id={source.id})")
                continue
            if not source.remote.digest:
                errors.append(f"remote source without digest (id={source.id})")
                continue
            if not source.remote.signature_hash:
                errors.append(
                    f"remote source without signatureHash (id={source.id})"
                )
                continue
            if source.remote.origin not in allowed_origins:
                errors.append(
                    f"remote origin not pre-bound/allowed: {source.remote.origin} "
                    f"(id={source.id})"
                )
                continue
        validated.append(source)

    if errors:
        return _blocked_resolution(tuple(errors), (), None)

    ordered = sorted(
        validated, key=lambda s: (s.priority, s.id)
    )
    present_kinds = _unique_kinds_in_order(ordered)

    merged: dict[str, Any] = {}
    for source in ordered:
        merged = merge_values(merged, source.values)

    resolved_hash = hash_value(merged)

    source_hashes = tuple(
        SourceHashRecord(
            id=s.id,
            kind=s.kind,
            revision=s.revision,
            content_hash=s.content_hash,
            schema_hash=s.schema_hash,
            priority=s.priority,
            remote_origin=s.remote.origin if s.remote else None,
            remote_digest=s.remote.digest if s.remote else None,
        )
        for s in ordered
    )

    schema_hashes = {s.schema_hash for s in ordered}
    if len(schema_hashes) > 1:
        drift = ConfigDriftRecord(
            kind="schema-drift",
            detail=f"sources disagree on schemaHash: {', '.join(sorted(schema_hashes))}",
            expected_hash=None,
            actual_hash=resolved_hash,
        )
        return _blocked_resolution((drift.detail,), source_hashes, drift)

    schema_hash = ordered[0].schema_hash if ordered else ""

    if options.schema_fields is not None:
        expected_schema_hash = schema_hash_from_fields(options.schema_fields)
        if schema_hash and schema_hash != expected_schema_hash:
            drift = ConfigDriftRecord(
                kind="schema-drift",
                detail=f"schemaHash mismatch: expected {expected_schema_hash}, got {schema_hash}",
                expected_hash=None,
                actual_hash=resolved_hash,
            )
            return _blocked_resolution((drift.detail,), source_hashes, drift)

    if options.expected_receipt_hash and options.expected_receipt_hash != resolved_hash:
        drift = ConfigDriftRecord(
            kind="content-drift",
            detail=f"resolved hash {resolved_hash} != expected {options.expected_receipt_hash}",
            expected_hash=options.expected_receipt_hash,
            actual_hash=resolved_hash,
        )
        return ConfigResolutionContract(
            status="CONTRADICTED",
            source_order=present_kinds,
            source_hashes=source_hashes,
            schema_hash=schema_hash,
            resolved_hash=resolved_hash,
            resolved={},
            drift=drift,
            errors=(drift.detail,),
        )

    return ConfigResolutionContract(
        status="RESOLVED",
        source_order=present_kinds,
        source_hashes=source_hashes,
        schema_hash=schema_hash,
        resolved_hash=resolved_hash,
        resolved=merged,
        drift=None,
        errors=(),
    )


def compute_receipt_hash(sources: list[ConfigSourceContract]) -> str:
    ordered = sorted(sources, key=lambda s: (s.priority, s.id))
    merged: dict[str, Any] = {}
    for source in ordered:
        merged = merge_values(merged, source.values)
    return hash_value(merged)


def canonical_source_order() -> list[ConfigSourceKind]:
    return list(SOURCE_ORDER)


def is_safe_to_advance(contract: ConfigResolutionContract) -> bool:
    return (
        contract.status == "RESOLVED"
        and not contract.errors
        and contract.drift is None
    )


def _unique_kinds_in_order(
    ordered: list[ConfigSourceContract],
) -> tuple[ConfigSourceKind, ...]:
    seen: set[str] = set()
    out: list[ConfigSourceKind] = []
    for s in ordered:
        if s.kind not in seen:
            seen.add(s.kind)
            out.append(s.kind)
    return tuple(out)


def _blocked_resolution(
    errors: tuple[str, ...],
    source_hashes: tuple[SourceHashRecord, ...],
    drift: Optional[ConfigDriftRecord],
) -> ConfigResolutionContract:
    return ConfigResolutionContract(
        status="BLOCKED",
        source_order=(),
        source_hashes=source_hashes,
        schema_hash="",
        resolved_hash="",
        resolved={},
        drift=drift,
        errors=errors,
    )


__all__ = [
    "ResolveOptions",
    "resolve_config_sources",
    "compute_receipt_hash",
    "canonical_source_order",
    "is_safe_to_advance",
    "default_priority_for",
]
