#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_exact(relative: str, old: str, new: str) -> None:
    target = ROOT / relative
    content = target.read_text(encoding='utf-8')
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f'{relative}: expected one occurrence, found {count}: {old!r}')
    target.write_text(content.replace(old, new, 1), encoding='utf-8')


def main() -> None:
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
    replace_exact(runtime, "    executor: input.executor || 'sovereign-agent',", "    executor: input.executor || 'sovereign-local-runner',")
    replace_exact(runtime, "    workspaceHost: input.workspaceHost || 'external-agent-runtime',", "    workspaceHost: input.workspaceHost || 'managed-ephemeral',")
    replace_exact(runtime, "    executor: input.executor || 'sovereign-agent',", "    executor: input.executor || 'sovereign-local-runner',")

    test_file = 'src/features/product/runtime/agentWorkspaceRuntime.test.ts'
    test_target = ROOT / test_file
    test_content = test_target.read_text(encoding='utf-8')
    test_content = test_content.replace('Sovereign Agent workspace request', 'internal Sovereign Agent workspace request')
    test_content = test_content.replace("expect(request.executor).toBe('sovereign-agent');", "expect(request.executor).toBe('sovereign-local-runner');")
    test_content = test_content.replace("expect(request.workspaceHost).toBe('external-agent-runtime');", "expect(request.workspaceHost).toBe('managed-ephemeral');")
    test_content = test_content.replace("expect(decision.executor).toBe('sovereign-agent');", "expect(decision.executor).toBe('sovereign-local-runner');")
    test_target.write_text(test_content, encoding='utf-8')

    for relative in ['backend/agent_runtime/routes.py', 'scripts/sovereign-backend/agent_runtime/routes.py']:
        target = ROOT / relative
        content = target.read_text(encoding='utf-8')
        content = content.replace(
            'thin and prevents OpenHands-specific routes from becoming the truth source.',
            'thin and keeps the internal Sovereign Agent routes as the only job truth source.',
        )
        target.write_text(content, encoding='utf-8')

    print('SOVEREIGN_AGENT_INTERNAL_CONTRACT=FINALIZED')


if __name__ == '__main__':
    main()
