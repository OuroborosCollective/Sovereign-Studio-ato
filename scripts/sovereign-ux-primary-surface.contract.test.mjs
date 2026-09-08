import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

describe('Sovereign chat-first primary-surface contract', () => {
  it('mounts Play Release as current-session truth while preserving the observatory route', () => {
    const app = source('src/App.tsx');

    expect(app).toContain('PlayReleaseChat');
    expect(app).toContain('data-testid="sovereign-chat-app"');
    expect(app).toContain('data-layout="chat-first-agent-zero-background"');
    expect(app).toContain('data-primary-surface="play-release-chat"');
    expect(app).toContain('data-truth-scope="current-chat-session-only"');
    expect(app).toContain('aria-label="Sovereign Chat"');
    expect(app).not.toContain('BuilderContainer');
    expect(app).not.toContain('RESTORE_LATEST_JOB');
    expect(app).not.toContain('data-layout="monitor-first-live-workspace"');

    expect(app).toContain('EvidenceObservatoryAtlas');
    expect(app).toContain("window.location.pathname === '/observatory'");
    expect(app).toContain("window.location.pathname === '/evidence-observatory'");
    expect(app).toContain("new URLSearchParams(window.location.search).get('observatory') === '1'");
  });

  it('keeps mission execution and Draft-PR creation on the real release-chat runtime path', () => {
    const release = source('src/features/release/PlayReleaseChat.tsx');

    expect(release).toContain('evaluateInputPolicy(text)');
    expect(release).toContain('fetchSovereignDirectLlmInterpretation');
    expect(release).toContain('deriveRepositoryActionFallback');
    expect(release).toContain('pendingRepositoryAction');
    expect(release).toContain('confirmPendingRepositoryAction');
    expect(release).toContain('startRepositoryExecution');
    expect(release).toContain('prepareDraftPr');
    expect(release).toContain('createDraftPr');
    expect(release).toContain('Draft PR erstellen');
    expect(release).toContain('readbackHeadSha');
  });

  it('does not auto-adopt historic Agent jobs into the current release session', () => {
    const app = source('src/App.tsx');
    const release = source('src/features/release/PlayReleaseChat.tsx');

    expect(app).not.toContain('RESTORE_LATEST_JOB');
    expect(release).not.toContain('listJobs(');
    expect(release).not.toContain('RESTORE_LATEST_JOB');
  });
});
