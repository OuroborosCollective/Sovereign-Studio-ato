import { describe, expect, it } from 'vitest';
import {
  buildAgentWorkspaceRequest,
  classifyWorkspaceIntent,
  decideAgentWorkspaceIntent,
  normalizeAgentWorkspaceResult,
  normalizeWorkspacePath,
  sanitizeWorkspaceText,
  shouldCleanupWorkspace,
  validateAgentWorkspaceRequest,
} from './agentWorkspaceRuntime';

function validRequest() {
  return buildAgentWorkspaceRequest({
    repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    branch: 'main',
    task: 'Implementiere einen Fix in src/features/product/runtime/example.ts und ergänze Tests.',
    allowedPaths: ['src/', 'tests/'],
    forbiddenPaths: ['docs/SOVEREIGN_PLAN.md'],
    memoryHints: ['Nutze Runtime-Wahrheit statt UI-Wahrheit.'],
  });
}

describe('agentWorkspaceRuntime', () => {
  it('builds a Draft-PR-only OpenHands workspace request by default', () => {
    const request = validRequest();

    expect(request.executor).toBe('openhands');
    expect(request.draftPrOnly).toBe(true);
    expect(request.workspaceHost).toBe('external-agent-runtime');
    expect(validateAgentWorkspaceRequest(request).allowed).toBe(true);
  });

  it('blocks invalid repo urls, empty tasks and non-draft execution', () => {
    const result = validateAgentWorkspaceRequest({
      ...validRequest(),
      repoUrl: 'http://example.com/not-github',
      task: '',
      draftPrOnly: false as true,
    });

    expect(result.allowed).toBe(false);
    expect(result.blockers).toContain('Workspace requires a valid HTTPS GitHub repository URL.');
    expect(result.blockers).toContain('Workspace task is required.');
    expect(result.blockers).toContain('Workspace may only run in Draft-PR-only mode.');
  });

  it('rejects unsafe workspace paths', () => {
    const result = validateAgentWorkspaceRequest({
      ...validRequest(),
      allowedPaths: ['src/', '../secret'],
    });

    expect(result.allowed).toBe(false);
    expect(result.blockers).toContain('Workspace allowedPaths contains an unsafe path.');
  });

  it('sanitizes secret-like values before events or results are displayed', () => {
    expect(sanitizeWorkspaceText('Authorization: Bearer ghp_1234567890123456789012345')).toContain('[redacted]');
    expect(sanitizeWorkspaceText('token=sk-proj-abcdefghijklmnopqrstuvwxyz')).toContain('[redacted]');
  });

  it('blocks requests that still contain secret-like values', () => {
    const result = validateAgentWorkspaceRequest({
      ...validRequest(),
      task: 'Fix build with token=ghp_1234567890123456789012345',
    });

    expect(result.allowed).toBe(false);
    expect(result.blockers).toContain('Workspace request contains a secret-like value and must be sanitized before dispatch.');
  });

  it('keeps casual and read-only chat away from write workspaces', () => {
    expect(classifyWorkspaceIntent('Warum ist der Worker blockiert?')).toBe('read-only');
    expect(classifyWorkspaceIntent('Erzähl mir einen Witz über Code.')).toBe('none');

    const decision = decideAgentWorkspaceIntent({
      message: 'Warum ist der Worker blockiert?',
      repoReady: true,
      executorReady: true,
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('Read-only chat');
  });

  it('allows explicit code work when repo and executor are ready', () => {
    const decision = decideAgentWorkspaceIntent({
      message: 'Implementiere einen Fix in src/features/product/runtime/agentWorkspaceRuntime.ts und ergänze Tests.',
      repoReady: true,
      executorReady: true,
      activeWorkspaceStatus: 'idle',
    });

    expect(decision.kind).toBe('code-execution');
    expect(decision.allowed).toBe(true);
    expect(decision.executor).toBe('openhands');
  });

  it('blocks code work without repo or while another workspace is running', () => {
    expect(decideAgentWorkspaceIntent({
      message: 'Fix src/App.tsx und erstelle einen Draft PR.',
      repoReady: false,
      executorReady: true,
    }).reason).toContain('loaded repository');

    expect(decideAgentWorkspaceIntent({
      message: 'Fix src/App.tsx und erstelle einen Draft PR.',
      repoReady: true,
      executorReady: true,
      activeWorkspaceStatus: 'running',
    }).reason).toContain('already running');
  });

  it('normalizes workspace results and drops unsafe file paths', () => {
    const result = normalizeAgentWorkspaceResult({
      workspaceId: 'job 123 !',
      status: 'completed',
      changedFiles: ['src/App.tsx', '../secret.env', 'tests/App.test.tsx', 'src/App.tsx'],
      diffSummary: 'Updated code with password=super-secret',
      blocker: 'No blocker. Authorization: Bearer abcdefghijklmnopqrstuvwxyz',
      draftPrUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/123',
      workspaceInspectorUrl: 'https://openhands.example/workspaces/job-123',
      events: [{ level: 'info', message: 'token=sk-proj-abcdefghijklmnopqrstuvwxyz', at: 1 }],
    });

    expect(result.workspaceId).toBe('job-123--');
    expect(result.changedFiles).toEqual(['src/App.tsx', 'tests/App.test.tsx']);
    expect(result.diffSummary).toContain('[redacted]');
    expect(result.blocker).toContain('[redacted]');
    expect(result.events[0]?.message).toContain('[redacted]');
    expect(result.draftPrUrl).toContain('/pull/123');
  });

  it('knows which terminal states require cleanup', () => {
    expect(shouldCleanupWorkspace('completed')).toBe(true);
    expect(shouldCleanupWorkspace('failed')).toBe(true);
    expect(shouldCleanupWorkspace('blocked')).toBe(true);
    expect(shouldCleanupWorkspace('running')).toBe(false);
    expect(shouldCleanupWorkspace('cleaned')).toBe(false);
  });

  it('normalizes only safe relative paths', () => {
    expect(normalizeWorkspacePath('./src/App.tsx')).toBe('src/App.tsx');
    expect(normalizeWorkspacePath('/etc/passwd')).toBeNull();
    expect(normalizeWorkspacePath('src/../secret.ts')).toBeNull();
  });

  it('casual chat does not start workspace', () => {
    const casualMessages = [
      'Hallo, wie geht es dir?',
      'Was ist Sovereign Studio?',
      'Erzähl mir mehr über KI.',
      'Kannst du mir bei anderen Projekten helfen?',
      'Wie funktioniert das hier?',
    ];

    for (const msg of casualMessages) {
      const decision = decideAgentWorkspaceIntent({
        message: msg,
        repoReady: true,
        executorReady: true,
      });
      expect(decision.allowed).toBe(false);
      expect(decision.kind).not.toBe('code-execution');
    }
  });

  it('read-only Worker diagnostic does not start workspace', () => {
    const readOnlyMessages = [
      'Was ist der Worker-Status?',
      'Erkläre mir die Fehlermeldung.',
      'Prüfe die Health-Status.',
      'Warum ist der Worker blockiert?',
      'Lies die Logs und erkläre sie.',
    ];

    for (const msg of readOnlyMessages) {
      const decision = decideAgentWorkspaceIntent({
        message: msg,
        repoReady: true,
        executorReady: true,
      });
      expect(decision.allowed).toBe(false);
      expect(decision.kind).toBe('read-only');
    }
  });

  it('repo missing blocks workspace', () => {
    const decision = decideAgentWorkspaceIntent({
      message: 'Implementiere einen Bug-Fix in src/App.tsx.',
      repoReady: false,
      executorReady: true,
    });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('loaded repository');
  });

  it('executor missing blocks workspace', () => {
    const decision = decideAgentWorkspaceIntent({
      message: 'Implementiere einen Bug-Fix in src/App.tsx.',
      repoReady: true,
      executorReady: false,
    });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('executor');
  });

  it('another active workspace blocks new workspace', () => {
    for (const status of ['queued', 'running'] as const) {
      const decision = decideAgentWorkspaceIntent({
        message: 'Erstelle einen Draft PR für den Fix.',
        repoReady: true,
        executorReady: true,
        activeWorkspaceStatus: status,
      });
      expect(decision.allowed).toBe(false);
      expect(decision.reason).toContain('already');
    }
  });

  it('blocked workspace status allows retry', () => {
    const decision = decideAgentWorkspaceIntent({
      message: 'Erstelle einen Draft PR für den Fix.',
      repoReady: true,
      executorReady: true,
      activeWorkspaceStatus: 'blocked',
    });
    expect(decision.allowed).toBe(true);
  });

  it('cleaned workspace allows new workspace', () => {
    const decision = decideAgentWorkspaceIntent({
      message: 'Erstelle einen Draft PR für den Fix.',
      repoReady: true,
      executorReady: true,
      activeWorkspaceStatus: 'cleaned',
    });
    expect(decision.allowed).toBe(true);
  });
});
