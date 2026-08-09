"""Configuration Provenance package - canonical backend implementation.

Deterministic, revisions/schema/source-bound configuration resolution with
redacted receipts and PatchMon readback. Mirrors the TypeScript core in
``src/runtime/config``. Mutation of configuration runs through #1119; this
package is read-only resolution + provenance only.
"""

from .config_sources import (
    ALLOWED_SOURCE_KINDS,
    ConfigDriftRecord,
    ConfigResolutionContract,
    ConfigSchemaDescriptor,
    ConfigSchemaField,
    ConfigSourceContract,
    ConfigSourceKind,
    DriftKind,
    RedactedSecret,
    RemoteBinding,
    ResolutionStatus,
    SOURCE_ORDER,
    SOURCE_PRIORITY,
    SourceHashRecord,
    default_priority_for,
    is_allowed_source_kind,
)
from .config_canonicalize import (
    canonical_json,
    hash_string,
    hash_value,
    is_redacted_secret,
    merge_values,
    schema_hash_from_fields,
)
from .resolver import (
    ResolveOptions,
    canonical_source_order,
    compute_receipt_hash,
    is_safe_to_advance,
    resolve_config_sources,
)
from .receipt import (
    DETERMINISTIC_EPOCH,
    ConfigReceipt,
    ReceiptOptions,
    compute_receipt_hash as compute_public_receipt_hash,
    materialize_receipt,
    verify_receipt,
)

__all__ = [
    "ALLOWED_SOURCE_KINDS",
    "ConfigDriftRecord",
    "ConfigReceipt",
    "ConfigResolutionContract",
    "ConfigSchemaDescriptor",
    "ConfigSchemaField",
    "ConfigSourceContract",
    "ConfigSourceKind",
    "DETERMINISTIC_EPOCH",
    "DriftKind",
    "RedactedSecret",
    "ReceiptOptions",
    "RemoteBinding",
    "ResolveOptions",
    "ResolutionStatus",
    "SOURCE_ORDER",
    "SOURCE_PRIORITY",
    "SourceHashRecord",
    "canonical_json",
    "canonical_source_order",
    "compute_receipt_hash",
    "compute_public_receipt_hash",
    "default_priority_for",
    "hash_string",
    "hash_value",
    "is_allowed_source_kind",
    "is_redacted_secret",
    "is_safe_to_advance",
    "materialize_receipt",
    "merge_values",
    "resolve_config_sources",
    "schema_hash_from_fields",
    "verify_receipt",
]
