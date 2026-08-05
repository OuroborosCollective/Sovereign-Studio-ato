from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Mapping


class PolicyLevel(IntEnum):
    MODEL_SUGGESTION = 10
    ADAPTER_HINT = 20
    SKILL_POLICY = 30
    TOOL_POLICY = 40
    RUNTIME_POLICY = 50
    OWNER_POLICY = 60


@dataclass(frozen=True, slots=True)
class PolicyRule:
    key: str
    value: str
    level: PolicyLevel
    source_path: str
    source_hash: str


@dataclass(frozen=True, slots=True)
class PolicyResolution:
    effective: Mapping[str, PolicyRule]
    rejected: tuple[PolicyRule, ...]


def resolve_policy_hierarchy(rules: Iterable[PolicyRule]) -> PolicyResolution:
    """Resolve policy deterministically; lower layers can never replace higher ones."""
    ordered = sorted(
        rules,
        key=lambda item: (-int(item.level), item.key, item.source_path, item.source_hash, item.value),
    )
    effective: dict[str, PolicyRule] = {}
    rejected: list[PolicyRule] = []
    for rule in ordered:
        if not rule.key or not rule.source_path or not rule.source_hash:
            raise ValueError("policy rules require key, source path and source hash")
        current = effective.get(rule.key)
        if current is None:
            effective[rule.key] = rule
            continue
        rejected.append(rule)
    return PolicyResolution(effective=effective, rejected=tuple(rejected))


def assert_policy_hashes(resolution: PolicyResolution, expected: Mapping[str, str]) -> None:
    for key, expected_hash in expected.items():
        rule = resolution.effective.get(key)
        if rule is None or rule.source_hash != expected_hash:
            raise ValueError(f"policy hash mismatch for {key}")
