"""Sovereign progressive skill runtime.

This package extends the existing agent runtime. It does not own workflow,
permission, credential, CAS, mutation-evidence or truth-store responsibilities.
"""

from .execution_mode import ModeTransition, validate_mode_transition, visible_effects_for_mode
from .manifest import (
    EffectClass,
    ReferenceLoadPolicy,
    SCHEMA_VERSION,
    SkillContractError,
    SkillMode,
    SourceKind,
    SovereignSkillManifestV1,
    parse_manifest,
)
from .policy_hierarchy import PolicyLevel, PolicyResolution, PolicyRule, resolve_policy_hierarchy
from .progressive_loader import LoadedSkillContext, ProgressiveLoadError, load_references
from .resolver import CandidateStatus, SkillCandidateDecision, resolve_candidate, select_one

__all__ = [
    "CandidateStatus",
    "EffectClass",
    "LoadedSkillContext",
    "ModeTransition",
    "PolicyLevel",
    "PolicyResolution",
    "PolicyRule",
    "ProgressiveLoadError",
    "ReferenceLoadPolicy",
    "SCHEMA_VERSION",
    "SkillCandidateDecision",
    "SkillContractError",
    "SkillMode",
    "SourceKind",
    "SovereignSkillManifestV1",
    "load_references",
    "parse_manifest",
    "resolve_candidate",
    "resolve_policy_hierarchy",
    "select_one",
    "validate_mode_transition",
    "visible_effects_for_mode",
]
