import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function source(relativePath: string): string {
  return readFileSync(join(process.cwd(), relativePath), 'utf8');
}

describe('Sovereign Control Surface vNext truth contract', () => {
  it('keeps every production effect behind the single live HTTP adapter with no simulator fallback', () => {
    const contract = source('src/features/control-surface-vnext/adapter/interface.ts');
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    const context = source('src/features/control-surface-vnext/adapter/context.tsx');

    expect(contract).toContain("mode: 'live_http'");
    expect(contract).toContain('isFallback: false');
    expect(context).toContain('new SovereignProductionAdapter()');
    for (const forbidden of [
      'MockSovereignBackendAdapter',
      'fallbackMock',
      '/api/config/',
      '/api/user/agent/swarm/job/',
      'sessionToken',
      'Authorization: `Bearer',
      'localStorage',
    ]) {
      expect(adapter, `forbidden production-adapter token: ${forbidden}`).not.toContain(forbidden);
    }
  });

  it('binds the exact persisted-run, linked-job, evidence and Draft-PR contracts already owned by the backend', () => {
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    const client = source('src/features/product/runtime/sovereignAgentClient.ts');

    for (const token of [
      "'/api/user/agent/swarm/run'",
      '/api/user/agent/swarm/runs/${encodeURIComponent(requested)}',
      "'/api/user/agent/toolchain/manifest'",
      "'/api/user/agent/swarm/manifest'",
      'this.client.getJob(run.jobId)',
      'this.client.getEvidenceAnchors(run.jobId)',
      'this.client.prepareDraftPr(run.jobId)',
      'this.client.createDraftPr(run.jobId)',
    ]) expect(adapter).toContain(token);

    for (const strictReadback of [
      'draftVerified',
      'readbackVerified',
      'checksReadbackVerified',
      'publishedHeadSha',
      'readbackHeadSha',
      "pullRequestState !== 'open'",
      'prDraft !== true',
    ]) expect(client).toContain(strictReadback);
  });

  it('does not elevate an observed job Draft-PR URL into verified publication state', () => {
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    expect(adapter).toContain('OBSERVED: backend job reports Draft PR URL');
    expect(adapter).toContain('const publication = this.publications.get(runId)');
    expect(adapter).toContain('this.publications.set(runId, publication)');
    expect(adapter).not.toContain('publication: snapshot?.draftPrUrl');
  });

  it('requires a separate visible Draft-PR gate and explicit external-write consent before creation', () => {
    const inspector = source('src/features/control-surface-vnext/components/PublicationInspector/PublicationInspector.tsx');
    expect(inspector).toContain('READ DRAFT-PR GATE');
    expect(inspector).toContain('EXTERNAL WRITE CONSENT');
    expect(inspector).toContain('create exactly one GitHub');
    expect(inspector).toContain('No merge. No push to main.');
    expect(inspector).toContain('Success is shown only after independent GitHub readback.');
    expect(inspector).toContain('DECLINE');
    expect(inspector).toContain('CREATE DRAFT PR');
  });

  it('keeps decorative biomodular effects explicitly non-authoritative', () => {
    const eye = source('src/features/control-surface-vnext/components/CyborgOcularMatrix/CyborgOcularMatrix.tsx');
    const neural = source('src/features/control-surface-vnext/components/RuntimeMonitor/NeuralLoadMonitor.tsx');
    const workspace = source('src/features/control-surface-vnext/components/WorkspaceProjection/WorkspaceProjection.tsx');

    expect(eye).toContain('EFFECTS DECORATIVE · STATE READBACK');
    expect(neural).toContain('UI PROJECTION · NOT CPU TELEMETRY');
    expect(neural).not.toContain('Math.random');
    expect(workspace).toContain('REVISION UNVERIFIED');
    expect(workspace).toContain('This does not claim the repository is globally clean.');
  });
});
