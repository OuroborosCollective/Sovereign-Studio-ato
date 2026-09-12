import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

describe('Sovereign vNext primary-surface contract', () => {
  it('mounts the runtime-readback control surface while preserving the observatory route', () => {
    const app = source('src/App.tsx');

    expect(app).toContain('SovereignControlSurfaceVNext');
    expect(app).toContain('data-testid="sovereign-chat-app"');
    expect(app).toContain('data-layout="sovereign-control-surface-vnext"');
    expect(app).toContain('data-primary-surface="sovereign-control-surface-vnext"');
    expect(app).toContain('data-truth-scope="runtime-readback-only"');
    expect(app).toContain('aria-label="Sovereign Control Surface"');
    expect(app).not.toContain('PlayReleaseChat');
    expect(app).not.toContain('BuilderContainer');
    expect(app).not.toContain('RESTORE_LATEST_JOB');

    expect(app).toContain('EvidenceObservatoryAtlas');
    expect(app).toContain("window.location.pathname === '/observatory'");
    expect(app).toContain("window.location.pathname === '/evidence-observatory'");
    expect(app).toContain("new URLSearchParams(window.location.search).get('observatory') === '1'");
  });

  it('keeps mission execution and Draft-PR creation behind the real production adapter and existing strict client', () => {
    const surface = source('src/features/control-surface-vnext/App.tsx');
    const repositoryAdapter = source('src/features/control-surface-vnext/adapter/repository-bound-adapter.ts');
    const adapterBase = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    const client = source('src/features/product/runtime/sovereignAgentClient.ts');
    const publication = source('src/features/control-surface-vnext/components/PublicationInspector/PublicationInspector.tsx');

    expect(surface).toContain('useSwarmRun');
    expect(surface).toContain('useSovereignJob');
    expect(surface).toContain('setActiveRunId(accepted.jobId)');
    expect(repositoryAdapter).toContain("'/api/user/agent/repository/run'");
    expect(repositoryAdapter).not.toContain("'/api/user/agent/swarm/run'");
    expect(adapterBase).toContain('this.client.prepareDraftPr(jobId)');
    expect(adapterBase).toContain('this.client.createDraftPr(jobId)');
    expect(client).toContain("jobPath(jobId, '/draft-pr/prepare')");
    expect(client).toContain("jobPath(jobId, '/draft-pr/create')");
    expect(client).toContain("stringValue(signal.prStateVerified) === 'open'");
    expect(client).toContain('signal.readbackVerified === true');
    expect(publication).toContain('EXTERNAL WRITE CONSENT');
    expect(publication).toContain('CREATE DRAFT PR');
  });

  it('does not auto-adopt historic Agent jobs or mount the retired chat as current truth', () => {
    const app = source('src/App.tsx');
    const surface = source('src/features/control-surface-vnext/App.tsx');
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');

    expect(app).not.toContain('RESTORE_LATEST_JOB');
    expect(surface).not.toContain('listJobs(');
    expect(surface).not.toContain('RESTORE_LATEST_JOB');
    expect(adapter).not.toContain('MockSovereignBackendAdapter');
    expect(adapter).not.toContain('fallbackMock');
  });
});
