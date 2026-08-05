from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Callable, Iterable

from .manifest import ReferenceLoadPolicy, SovereignSkillManifestV1


class ProgressiveLoadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedSkillContext:
    repository_revision: str
    path: str
    declared_blob_hash: str
    observed_sha256: str
    owner: str
    trust_class: str
    truth_boundary: str
    skill_id: str
    manifest_hash: str
    workflow_step: str
    load_reason: str
    content: str


ReadBoundContent = Callable[[str, str], bytes]


def _expected_sha256(identity: str) -> str | None:
    if identity.startswith("sha256:"):
        return identity.removeprefix("sha256:")
    if len(identity) == 64:
        return identity
    return None


def load_references(
    manifest: SovereignSkillManifestV1,
    *,
    repository_revision: str,
    owner: str,
    trust_class: str,
    truth_boundary: str,
    workflow_step: str,
    load_reason: str,
    read_bound_content: ReadBoundContent,
    matched: bool = False,
    explicit_paths: Iterable[str] = (),
) -> tuple[LoadedSkillContext, ...]:
    """Load only selected, revision-bound references after candidate resolution."""
    if trust_class not in {"owner", "runtime_attested", "repository_attested"}:
        raise ProgressiveLoadError("untrusted context cannot load skill references")
    if not repository_revision or not owner or not workflow_step or not load_reason:
        raise ProgressiveLoadError("repository revision, owner, workflow step and load reason are required")

    explicit = frozenset(explicit_paths)
    loaded: list[LoadedSkillContext] = []
    for reference in manifest.references:
        should_load = (
            (reference.load_policy is ReferenceLoadPolicy.ON_MATCH and matched)
            or (reference.load_policy is ReferenceLoadPolicy.ON_STEP and workflow_step == reference.path)
            or (reference.load_policy is ReferenceLoadPolicy.EXPLICIT_ONLY and reference.path in explicit)
        )
        if not should_load:
            continue

        raw = read_bound_content(reference.path, repository_revision)
        if not isinstance(raw, bytes):
            raise ProgressiveLoadError("reference reader must return bytes")
        observed_sha256 = hashlib.sha256(raw).hexdigest()
        expected_sha256 = _expected_sha256(reference.blob_hash)
        if expected_sha256 is not None and not hmac.compare_digest(expected_sha256, observed_sha256):
            raise ProgressiveLoadError(f"reference hash mismatch for {reference.path}")

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProgressiveLoadError(f"reference is not UTF-8: {reference.path}") from exc

        loaded.append(
            LoadedSkillContext(
                repository_revision=repository_revision,
                path=reference.path,
                declared_blob_hash=reference.blob_hash,
                observed_sha256=observed_sha256,
                owner=owner,
                trust_class=trust_class,
                truth_boundary=truth_boundary,
                skill_id=manifest.skill_id,
                manifest_hash=manifest.manifest_hash,
                workflow_step=workflow_step,
                load_reason=load_reason,
                content=content,
            )
        )
    return tuple(loaded)
