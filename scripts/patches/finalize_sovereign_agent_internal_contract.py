#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_exact(relative: str, old: str, new: str, expected: int = 1) -> None:
    target = ROOT / relative
    content = target.read_text(encoding='utf-8')
    count = content.count(old)
    if count != expected:
        raise RuntimeError(f'{relative}: expected {expected} occurrence(s), found {count}: {old!r}')
    target.write_text(content.replace(old, new), encoding='utf-8')


def normalize_compound_identifiers() -> None:
    for target in (ROOT / 'src').rglob('*'):
        if not target.is_file() or target.suffix not in {'.ts', '.tsx', '.js', '.jsx', '.mjs'}:
            continue
        content = target.read_text(encoding='utf-8')
        content = re.sub(r'(?<=[A-Za-z0-9_$])Sovereign Agent', 'SovereignAgent', content)
        content = re.sub(r'Sovereign Agent(?=[A-Za-z0-9_$])', 'SovereignAgent', content)
        content = content.replace('scopedSovereignAgentJob', 'scopedAgentJob')
        content = content.replace('scopedSovereignAgentIsRunning', 'scopedAgentIsRunning')
        content = content.replace('showSovereignAgentBriefing', 'showAgentBriefing')
        target.write_text(content, encoding='utf-8')


def main() -> None:
    normalize_compound_identifiers()

    runtime = 'src/features/product/runtime/agentWorkspaceRuntime.ts'
    replace_exact(
        runtime,
        "export type AgentWorkspaceExecutor = 'sovereign-agent' | 'external-code-agent' | 'local-runner';",
        "export type AgentWorkspaceExecutor = 'sovereign-local-runner';",
    )
    replace_exact(
        runtime,
        "export type AgentWorkspaceHost = 'managed-ephemeral' | 'self-hosted-runner' | 'external-agent-runtime';",
        "export type AgentWorkspaceHost = 'managed-ephemeral' | 'self-hosted-runner';",
    )
    replace_exact(
        runtime,
        "  return value === 'sovereign-agent' || value === 'external-code-agent' || value === 'local-runner';",
        "  return value === 'sovereign-local-runner';",
    )
    replace_exact(
        runtime,
        "  return value === 'managed-ephemeral' || value === 'self-hosted-runner' || value === 'external-agent-runtime';",
        "  return value === 'managed-ephemeral' || value === 'self-hosted-runner';",
    )
    replace_exact(
        runtime,
        "    executor: input.executor || 'sovereign-agent',",
        "    executor: input.executor || 'sovereign-local-runner',",
        expected=2,
    )
    replace_exact(runtime, "    workspaceHost: input.workspaceHost || 'external-agent-runtime',", "    workspaceHost: input.workspaceHost || 'managed-ephemeral',")

    test_file = 'src/features/product/runtime/agentWorkspaceRuntime.test.ts'
    test_target = ROOT / test_file
    test_content = test_target.read_text(encoding='utf-8')
    test_content = test_content.replace('Sovereign Agent workspace request', 'internal Sovereign Agent workspace request')
    test_content = test_content.replace("expect(request.executor).toBe('sovereign-agent');", "expect(request.executor).toBe('sovereign-local-runner');")
    test_content = test_content.replace("expect(request.workspaceHost).toBe('external-agent-runtime');", "expect(request.workspaceHost).toBe('managed-ephemeral');")
    test_content = test_content.replace("expect(decision.executor).toBe('sovereign-agent');", "expect(decision.executor).toBe('sovereign-local-runner');")
    test_target.write_text(test_content, encoding='utf-8')

    for relative in [
        'src/features/product/components/WorkerBlockerCard.tsx',
        'src/features/product/components/WorkerBlockerCard.test.tsx',
        'src/features/product/containers/BuilderContainer.tsx',
    ]:
        target = ROOT / relative
        content = target.read_text(encoding='utf-8')
        for old, new in [
            ('onSovereignAgentInstead', 'onAgentInstead'),
            ('handleSovereignAgent', 'handleAgent'),
            ('canSovereignAgent', 'canAgent'),
        ]:
            content = content.replace(old, new)
        target.write_text(content, encoding='utf-8')

    registry = ROOT / 'src/features/launcher/launcherRegistry.ts'
    registry_lines = registry.read_text(encoding='utf-8').splitlines()
    agent_entry_lines = [line for line in registry_lines if 'agentToolEntry' in line]
    if len(agent_entry_lines) != 1:
        raise RuntimeError(f'launcherRegistry.ts: expected one orphan agentToolEntry, found {len(agent_entry_lines)}')
    registry.write_text('\n'.join(line for line in registry_lines if 'agentToolEntry' not in line) + '\n', encoding='utf-8')

    router = 'src/features/product/runtime/sovereignCapabilityRouter.ts'
    replace_exact(
        router,
        "const SOVEREIGN_AGENT_TOKENS = [\n  'sovereign-agent',\n];",
        "const SOVEREIGN_AGENT_TOKENS = [\n  'sovereign agent',\n  'sovereign-agent',\n];",
    )
    replace_exact(
        router,
        "    agent: 'Sovereign Agent Executor Route',",
        "    'sovereign-agent': 'Sovereign Agent Executor Route',",
    )
    replace_exact(
        router,
        "    agent: 'Sovereign Agent',",
        "    'sovereign-agent': 'Sovereign Agent',",
    )
    replace_exact(
        router,
        "reason: 'Sovereign Agent wurde ausdrücklich angefordert und ist als externer Adapter verfügbar.',",
        "reason: 'Sovereign Agent wurde ausdrücklich angefordert und ist als interne Runtime verfügbar.',",
    )

    client_test = ROOT / 'src/features/product/runtime/sovereignAgentClient.test.ts'
    client_test_content = client_test.read_text(encoding='utf-8')
    old_fetcher = 'const fetcher = vi.fn(async () =>'
    if client_test_content.count(old_fetcher) != 3:
        raise RuntimeError(f'sovereignAgentClient.test.ts: expected three fetcher mocks, found {client_test_content.count(old_fetcher)}')
    client_test.write_text(
        client_test_content.replace(
            old_fetcher,
            'const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>',
        ),
        encoding='utf-8',
    )

    for relative in ['backend/agent_runtime/routes.py', 'scripts/sovereign-backend/agent_runtime/routes.py']:
        target = ROOT / relative
        content = target.read_text(encoding='utf-8')
        old = 'thin and prevents OpenHands-specific routes from becoming the truth source.'
        if content.count(old) != 1:
            raise RuntimeError(f'{relative}: expected one retired route comment, found {content.count(old)}')
        target.write_text(
            content.replace(old, 'thin and keeps the internal Sovereign Agent routes as the only job truth source.', 1),
            encoding='utf-8',
        )

    print('SOVEREIGN_AGENT_INTERNAL_CONTRACT=FINALIZED')


if __name__ == '__main__':
    main()
