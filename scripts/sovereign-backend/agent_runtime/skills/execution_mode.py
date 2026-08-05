from __future__ import annotations

from dataclasses import dataclass

from .manifest import EffectClass, SkillMode, SovereignSkillManifestV1


@dataclass(frozen=True, slots=True)
class ModeTransition:
    current: SkillMode
    target: SkillMode
    owner_approved: bool = False
    permission_receipt_hash: str = ""
    cas_receipt_hash: str = ""
    runtime_readback_planned: bool = False


_ALLOWED_TRANSITIONS = {
    SkillMode.ASSESS: {SkillMode.ASSESS, SkillMode.PROPOSE},
    SkillMode.PROPOSE: {SkillMode.PROPOSE, SkillMode.ASSESS, SkillMode.APPLY},
    SkillMode.APPLY: {SkillMode.APPLY, SkillMode.PROPOSE, SkillMode.OPERATE},
    SkillMode.OPERATE: {SkillMode.OPERATE, SkillMode.ASSESS},
}


def validate_mode_transition(
    manifest: SovereignSkillManifestV1,
    transition: ModeTransition,
) -> None:
    if transition.target not in manifest.modes:
        raise ValueError("target mode is not declared by the skill manifest")
    if transition.target not in _ALLOWED_TRANSITIONS[transition.current]:
        raise ValueError("mode transition is not allowed")

    effects = {script.effect_class for script in manifest.scripts}
    if transition.target is SkillMode.ASSESS and effects - {EffectClass.READ_ONLY}:
        # The manifest may contain mutating scripts, but ASSESS cannot expose them.
        return
    if transition.target is SkillMode.PROPOSE:
        return
    if transition.target is SkillMode.APPLY:
        if not transition.owner_approved:
            raise ValueError("APPLY requires explicit owner approval")
        if not transition.permission_receipt_hash or not transition.cas_receipt_hash:
            raise ValueError("APPLY requires permission and CAS receipts")
        if EffectClass.EXTERNAL_MUTATION in effects:
            raise ValueError("APPLY cannot authorize external mutation scripts")
    if transition.target is SkillMode.OPERATE:
        if not transition.owner_approved:
            raise ValueError("OPERATE requires explicit owner approval")
        if not transition.permission_receipt_hash or not transition.cas_receipt_hash:
            raise ValueError("OPERATE requires permission and CAS receipts")
        if not transition.runtime_readback_planned:
            raise ValueError("OPERATE requires an independent runtime readback plan")


def visible_effects_for_mode(
    manifest: SovereignSkillManifestV1,
    mode: SkillMode,
) -> tuple[EffectClass, ...]:
    declared = {script.effect_class for script in manifest.scripts}
    allowed = {
        SkillMode.ASSESS: {EffectClass.READ_ONLY},
        SkillMode.PROPOSE: {EffectClass.READ_ONLY},
        SkillMode.APPLY: {EffectClass.READ_ONLY, EffectClass.WORKSPACE_MUTATION},
        SkillMode.OPERATE: {
            EffectClass.READ_ONLY,
            EffectClass.WORKSPACE_MUTATION,
            EffectClass.EXTERNAL_MUTATION,
        },
    }[mode]
    return tuple(sorted(declared & allowed, key=lambda item: item.value))
