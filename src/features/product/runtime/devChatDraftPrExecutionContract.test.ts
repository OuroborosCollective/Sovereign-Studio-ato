import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function source(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8');
}

describe('DevChat Draft PR execution contract', () => {
  it('keeps reviewable presets routed to the repository executor in the deferred Builder runtime', () => {
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    expect(builder).toContain("await startAgentFromText(submitted, 'code_execution')");
    expect(builder).toContain('Browser-ARE und lokale Code-Synthese werden übersprungen.');
    expect(builder).toContain("submittedText.includes('Risiko: reviewable_patch')");
    expect(builder).toContain('Vorgemerktes Review-Preset wird direkt über den Repository-Executor wiederaufgenommen');
  });

  it('keeps mission execution and Draft-PR publication on the vNext persisted run / linked-job identity', () => {
    const app = source('src/App.tsx');
    const surface = source('src/features/control-surface-vnext/App.tsx');
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    const repositoryAdapter = source('src/features/control-surface-vnext/adapter/repository-bound-adapter.ts');
    const client = source('src/features/product/runtime/sovereignAgentClient.ts');
    const runtime = source('src/features/product/runtime/sovereignAgentRuntime.ts');

    expect(app).toContain('SovereignControlSurfaceVNext');
    expect(app).toContain('data-layout="sovereign-control-surface-vnext"');
    expect(app).toContain('data-primary-surface="sovereign-control-surface-vnext"');
    expect(app).toContain('data-truth-scope="runtime-readback-only"');
    expect(app).not.toContain('RESTORE_LATEST_JOB');
    expect(app).not.toContain('BuilderContainer');

    expect(surface).toContain('setActiveRunId(accepted.jobId)');
    expect(surface).toContain('prepareDraftPr');
    expect(surface).toContain('publishDraftPr');
    expect(repositoryAdapter).toContain("'/api/user/agent/repository/run'");
    expect(repositoryAdapter).not.toContain("'/api/user/agent/swarm/run'");
    expect(repositoryAdapter).toContain("agentMode: 'single'");
    expect(adapter).toContain('if (isDirectRepositoryJobId(runId)) return this.getDirectRepositoryJob(runId);');
    expect(adapter).toContain("? runId\n      : (await this.getRun(runId)).jobId");
    expect(adapter).toContain('this.client.prepareDraftPr(jobId)');
    expect(adapter).toContain('this.client.createDraftPr(jobId)');
    expect(adapter).toContain('readbackHeadSha: pr.readbackHeadSha');
    expect(adapter).not.toContain('MockSovereignBackendAdapter');
    expect(adapter).not.toContain('/api/config/');

    expect(client).toContain("'/api/user/agent/repository/run'");
    expect(client).not.toContain("'/api/user/agent/swarm/run'");
    expect(client).toContain("mode: 'free'");
    expect(client).toContain("agentMode: 'single'");
    expect(client).toContain('expectedHeadSha: input.expectedHeadSha.trim()');
    expect(runtime).toContain('readSameOriginBackendUrl()');
  });

  it('binds the deferred repository snapshot to a real commit SHA', () => {
    const bridge = source('src/features/product/runtime/devChatWorkerBridge.ts');
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    expect(bridge).toContain('/commits/${encodeURIComponent(parsed.branch)}');
    expect(bridge).toContain("headSha: typeof commit.sha === 'string' ? commit.sha : undefined");
    expect(builder).toContain('expectedHeadSha: chatRepoSnapshot.headSha');
    expect(builder).toContain('githubAccessToken: githubTokenRef.current || undefined');
  });

  it('does not mount the retired Rescue/ReSecure overlay and does not fall back to a simulator on the primary vNext surface', () => {
    const app = source('src/App.tsx');
    const surface = source('src/features/control-surface-vnext/App.tsx');
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');

    expect(app).not.toContain('SovereignRescueOverlay');
    expect(app).not.toContain('<RescuePanel');
    expect(surface).toContain('SovereignAdapterProvider');
    expect(adapter).toContain('SovereignProductionAdapter');
    expect(adapter).toContain("mode: 'live_http'");
    expect(adapter).toContain('isFallback: false');
    expect(adapter).not.toContain('fallbackMock');
    expect(adapter).not.toContain('MockSovereignBackendAdapter');
  });

  it('requires a concrete action preview before menu or slash Draft PR publication in the deferred Builder', () => {
    const builder = source('src/features/product/containers/BuilderContainer.tsx');
    const preview = source('src/features/product/components/DraftPrActionPreview.tsx');

    expect(builder).toContain('const requestDraftPrActionPreview = () =>');
    expect(builder).toContain('setShowDraftPrActionPreview(true)');
    expect(builder).toContain('requestDraftPrActionPreview();');
    expect(builder).toContain('<DraftPrActionPreview');
    expect(builder).toContain('void publishConfirmedDraftPr();');
    expect(preview).toContain('role="alertdialog"');
    expect(preview).toContain('Draft PR nach Serverprüfung posten');
    expect(preview).toContain('expectedHeadSha');
  });
});
