from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "sovereign-skill.v1"
_HEX_40_OR_64 = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})$")
_SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,119}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")


class SkillContractError(ValueError):
    """Raised when a skill manifest cannot be trusted or normalized."""


class SkillMode(str, Enum):
    ASSESS = "ASSESS"
    PROPOSE = "PROPOSE"
    APPLY = "APPLY"
    OPERATE = "OPERATE"


class SourceKind(str, Enum):
    SOVEREIGN = "sovereign"
    ADAPTED_REFERENCE = "adapted_reference"
    EXTERNAL_ADAPTER = "external_adapter"


class ReferenceLoadPolicy(str, Enum):
    ON_MATCH = "on_match"
    ON_STEP = "on_step"
    EXPLICIT_ONLY = "explicit_only"


class EffectClass(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_MUTATION = "workspace_mutation"
    EXTERNAL_MUTATION = "external_mutation"


@dataclass(frozen=True, slots=True)
class SkillReference:
    path: str
    blob_hash: str
    load_policy: ReferenceLoadPolicy


@dataclass(frozen=True, slots=True)
class SkillScript:
    path: str
    blob_hash: str
    effect_class: EffectClass


@dataclass(frozen=True, slots=True)
class SovereignSkillManifestV1:
    schema_version: str
    skill_id: str
    version: str
    source_kind: SourceKind
    source_revision: str | None
    description: str
    triggers: tuple[str, ...]
    anti_triggers: tuple[str, ...]
    modes: tuple[SkillMode, ...]
    required_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    required_evidence: tuple[str, ...]
    references: tuple[SkillReference, ...]
    scripts: tuple[SkillScript, ...]
    owner_policy_hash: str

    @property
    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def effect_summary(self) -> tuple[str, ...]:
        return tuple(sorted({script.effect_class.value for script in self.scripts}))

    def summary(self) -> dict[str, Any]:
        """Return only the progressive-disclosure start envelope."""
        return {
            "schemaVersion": self.schema_version,
            "skillId": self.skill_id,
            "version": self.version,
            "description": self.description,
            "triggers": list(self.triggers),
            "antiTriggers": list(self.anti_triggers),
            "modes": [mode.value for mode in self.modes],
            "requiredCapabilities": list(self.required_capabilities),
            "forbiddenCapabilities": list(self.forbidden_capabilities),
            "effects": list(self.effect_summary),
            "manifestHash": self.manifest_hash,
        }

    def canonical_json(self) -> str:
        return json.dumps(to_wire(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_ALLOWED_FIELDS = {
    "schemaVersion",
    "skillId",
    "version",
    "sourceKind",
    "sourceRevision",
    "description",
    "triggers",
    "antiTriggers",
    "modes",
    "requiredCapabilities",
    "forbiddenCapabilities",
    "requiredEvidence",
    "references",
    "scripts",
    "ownerPolicyHash",
}
_REFERENCE_FIELDS = {"path", "blobHash", "loadPolicy"}
_SCRIPT_FIELDS = {"path", "blobHash", "effectClass"}


def _closed_fields(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SkillContractError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillContractError(f"{label} must be a non-empty string")
    return value.strip()


def _safe_path(value: Any, label: str) -> str:
    path = _required_text(value, label).replace("\\", "/")
    if path.startswith("/") or path.startswith("../") or "/../" in f"/{path}/" or "\x00" in path:
        raise SkillContractError(f"{label} must remain repository-relative")
    return path


def _hash(value: Any, label: str) -> str:
    normalized = _required_text(value, label).lower()
    if not _HEX_40_OR_64.fullmatch(normalized):
        raise SkillContractError(f"{label} must be a bound Git blob or SHA-256 identity")
    return normalized


def _string_tuple(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SkillContractError(f"{label} must be an array")
    normalized = tuple(_required_text(item, f"{label}[]") for item in value)
    if not allow_empty and not normalized:
        raise SkillContractError(f"{label} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise SkillContractError(f"{label} must not contain duplicates")
    return normalized


def parse_manifest(payload: Mapping[str, Any]) -> SovereignSkillManifestV1:
    if not isinstance(payload, Mapping):
        raise SkillContractError("manifest must be an object")
    _closed_fields(payload, _ALLOWED_FIELDS, "manifest")

    schema_version = _required_text(payload.get("schemaVersion"), "schemaVersion")
    if schema_version != SCHEMA_VERSION:
        raise SkillContractError(f"unsupported schemaVersion: {schema_version}")

    skill_id = _required_text(payload.get("skillId"), "skillId")
    if not _SKILL_ID.fullmatch(skill_id):
        raise SkillContractError("skillId is not canonical")

    version = _required_text(payload.get("version"), "version")
    if not _VERSION.fullmatch(version):
        raise SkillContractError("version must be semantic")

    source_kind = SourceKind(_required_text(payload.get("sourceKind"), "sourceKind"))
    source_revision_raw = payload.get("sourceRevision")
    source_revision = None if source_revision_raw in (None, "") else _hash(source_revision_raw, "sourceRevision")
    if source_kind is not SourceKind.SOVEREIGN and source_revision is None:
        raise SkillContractError("non-sovereign sources require sourceRevision")

    references_raw = payload.get("references")
    if not isinstance(references_raw, list):
        raise SkillContractError("references must be an array")
    references: list[SkillReference] = []
    for index, item in enumerate(references_raw):
        if not isinstance(item, Mapping):
            raise SkillContractError(f"references[{index}] must be an object")
        _closed_fields(item, _REFERENCE_FIELDS, f"references[{index}]")
        references.append(
            SkillReference(
                path=_safe_path(item.get("path"), f"references[{index}].path"),
                blob_hash=_hash(item.get("blobHash"), f"references[{index}].blobHash"),
                load_policy=ReferenceLoadPolicy(
                    _required_text(item.get("loadPolicy"), f"references[{index}].loadPolicy")
                ),
            )
        )

    scripts_raw = payload.get("scripts")
    if not isinstance(scripts_raw, list):
        raise SkillContractError("scripts must be an array")
    scripts: list[SkillScript] = []
    for index, item in enumerate(scripts_raw):
        if not isinstance(item, Mapping):
            raise SkillContractError(f"scripts[{index}] must be an object")
        _closed_fields(item, _SCRIPT_FIELDS, f"scripts[{index}]")
        scripts.append(
            SkillScript(
                path=_safe_path(item.get("path"), f"scripts[{index}].path"),
                blob_hash=_hash(item.get("blobHash"), f"scripts[{index}].blobHash"),
                effect_class=EffectClass(
                    _required_text(item.get("effectClass"), f"scripts[{index}].effectClass")
                ),
            )
        )

    modes_raw = _string_tuple(payload.get("modes"), "modes")
    modes = tuple(SkillMode(mode) for mode in modes_raw)
    required_capabilities = _string_tuple(
        payload.get("requiredCapabilities"), "requiredCapabilities", allow_empty=True
    )
    forbidden_capabilities = _string_tuple(
        payload.get("forbiddenCapabilities"), "forbiddenCapabilities", allow_empty=True
    )
    overlap = sorted(set(required_capabilities) & set(forbidden_capabilities))
    if overlap:
        raise SkillContractError(f"capabilities cannot be both required and forbidden: {', '.join(overlap)}")

    return SovereignSkillManifestV1(
        schema_version=schema_version,
        skill_id=skill_id,
        version=version,
        source_kind=source_kind,
        source_revision=source_revision,
        description=_required_text(payload.get("description"), "description"),
        triggers=_string_tuple(payload.get("triggers"), "triggers"),
        anti_triggers=_string_tuple(payload.get("antiTriggers"), "antiTriggers", allow_empty=True),
        modes=modes,
        required_capabilities=required_capabilities,
        forbidden_capabilities=forbidden_capabilities,
        required_evidence=_string_tuple(payload.get("requiredEvidence"), "requiredEvidence", allow_empty=True),
        references=tuple(references),
        scripts=tuple(scripts),
        owner_policy_hash=_hash(payload.get("ownerPolicyHash"), "ownerPolicyHash"),
    )


def to_wire(manifest: SovereignSkillManifestV1) -> dict[str, Any]:
    return {
        "schemaVersion": manifest.schema_version,
        "skillId": manifest.skill_id,
        "version": manifest.version,
        "sourceKind": manifest.source_kind.value,
        **({"sourceRevision": manifest.source_revision} if manifest.source_revision else {}),
        "description": manifest.description,
        "triggers": list(manifest.triggers),
        "antiTriggers": list(manifest.anti_triggers),
        "modes": [mode.value for mode in manifest.modes],
        "requiredCapabilities": list(manifest.required_capabilities),
        "forbiddenCapabilities": list(manifest.forbidden_capabilities),
        "requiredEvidence": list(manifest.required_evidence),
        "references": [
            {"path": item.path, "blobHash": item.blob_hash, "loadPolicy": item.load_policy.value}
            for item in manifest.references
        ],
        "scripts": [
            {"path": item.path, "blobHash": item.blob_hash, "effectClass": item.effect_class.value}
            for item in manifest.scripts
        ],
        "ownerPolicyHash": manifest.owner_policy_hash,
    }
