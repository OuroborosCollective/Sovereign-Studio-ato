from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .manifest import SovereignSkillManifestV1

_TOKEN = re.compile(r"[a-z0-9_.:/-]+", re.IGNORECASE)


class CandidateStatus(str, Enum):
    SELECTED = "SELECTED"
    NOT_MATCHED = "NOT_MATCHED"
    BLOCKED_ANTI_TRIGGER = "BLOCKED_ANTI_TRIGGER"
    BLOCKED_CONTEXT_TRUST = "BLOCKED_CONTEXT_TRUST"
    BLOCKED_CAPABILITY_STAGE = "BLOCKED_CAPABILITY_STAGE"
    BLOCKED_OWNER_POLICY = "BLOCKED_OWNER_POLICY"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class SkillCandidateDecision:
    skill_id: str
    manifest_hash: str
    status: CandidateStatus
    score: int
    matched_triggers: tuple[str, ...]
    matched_anti_triggers: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    reasons: tuple[str, ...]


def _normalized_text(value: str) -> str:
    return " ".join(_TOKEN.findall(value.casefold()))


def _matches(phrase: str, normalized_text: str) -> bool:
    normalized_phrase = _normalized_text(phrase)
    return bool(normalized_phrase) and normalized_phrase in normalized_text


def resolve_candidate(
    manifest: SovereignSkillManifestV1,
    *,
    request_text: str,
    staged_capabilities: Iterable[str],
    context_trust: str,
    owner_policy_hash: str,
) -> SkillCandidateDecision:
    """Resolve one skill candidate without authorizing a capability or effect."""
    normalized = _normalized_text(request_text)
    matched_triggers = tuple(sorted(trigger for trigger in manifest.triggers if _matches(trigger, normalized)))
    matched_anti = tuple(
        sorted(trigger for trigger in manifest.anti_triggers if _matches(trigger, normalized))
    )
    staged = frozenset(staged_capabilities)
    missing = tuple(sorted(set(manifest.required_capabilities) - staged))
    forbidden_staged = tuple(sorted(set(manifest.forbidden_capabilities) & staged))

    if owner_policy_hash != manifest.owner_policy_hash:
        return SkillCandidateDecision(
            manifest.skill_id,
            manifest.manifest_hash,
            CandidateStatus.BLOCKED_OWNER_POLICY,
            0,
            matched_triggers,
            matched_anti,
            missing,
            ("owner policy hash mismatch",),
        )
    if context_trust not in {"owner", "runtime_attested", "repository_attested"}:
        return SkillCandidateDecision(
            manifest.skill_id,
            manifest.manifest_hash,
            CandidateStatus.BLOCKED_CONTEXT_TRUST,
            0,
            matched_triggers,
            matched_anti,
            missing,
            ("context is not trusted for skill resolution",),
        )
    if matched_anti:
        return SkillCandidateDecision(
            manifest.skill_id,
            manifest.manifest_hash,
            CandidateStatus.BLOCKED_ANTI_TRIGGER,
            0,
            matched_triggers,
            matched_anti,
            missing,
            ("anti-trigger matched",),
        )
    if not matched_triggers:
        return SkillCandidateDecision(
            manifest.skill_id,
            manifest.manifest_hash,
            CandidateStatus.NOT_MATCHED,
            0,
            (),
            (),
            missing,
            ("no trigger matched",),
        )
    if missing or forbidden_staged:
        reasons = []
        if missing:
            reasons.append("required capabilities were not staged")
        if forbidden_staged:
            reasons.append("forbidden capabilities are present in the run envelope")
        return SkillCandidateDecision(
            manifest.skill_id,
            manifest.manifest_hash,
            CandidateStatus.BLOCKED_CAPABILITY_STAGE,
            0,
            matched_triggers,
            (),
            missing,
            tuple(reasons),
        )

    score = sum(len(_normalized_text(trigger).split()) for trigger in matched_triggers)
    return SkillCandidateDecision(
        manifest.skill_id,
        manifest.manifest_hash,
        CandidateStatus.SELECTED,
        score,
        matched_triggers,
        (),
        (),
        ("candidate selected; permission and effect gates remain separate",),
    )


def select_one(decisions: Iterable[SkillCandidateDecision]) -> SkillCandidateDecision | None:
    eligible = [decision for decision in decisions if decision.status is CandidateStatus.SELECTED]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (-item.score, item.skill_id, item.manifest_hash))
    if len(eligible) > 1 and eligible[0].score == eligible[1].score:
        first = eligible[0]
        return SkillCandidateDecision(
            first.skill_id,
            first.manifest_hash,
            CandidateStatus.AMBIGUOUS,
            first.score,
            first.matched_triggers,
            (),
            (),
            ("multiple candidates have the same deterministic score",),
        )
    return eligible[0]
