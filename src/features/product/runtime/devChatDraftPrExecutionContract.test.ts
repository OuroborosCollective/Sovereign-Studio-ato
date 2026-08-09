import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function source(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8');
}

describe('DevChat Draft PR execution contract', () => {
  it('routes reviewable presets directly to the repository executor instead of browser ARE', () => {
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    expect(builder).toContain("await startAgentFromText(submitted, 'code_execution')");
    expect(builder).toContain('Browser-ARE und lokale Code-Synthese werden übersprungen.');
    expect(builder).toContain("submittedText.includes('Risiko: reviewable_patch')");
    expect(builder).toContain('Vorgemerktes Review-Preset wird direkt über den Repository-Executor wiederaufgenommen');
  });

  it('starts the executable swarm, restores persisted jobs, and forwards GitHub access at publication', () => {
    const app = source('src/App.tsx');
    const client = source('src/features/product/runtime/sovereignAgentClient.ts');
    const runtime = source('src/features/product/runtime/sovereignAgentRuntime.ts');

    expect(app).toContain('agentClient.startRepositoryExecution({');
    expect(app).toContain('agentClient.listJobs()');
    expect(app).toContain('expectedHeadSha: input.expectedHeadSha');
    expect(app).toContain('agentClient.createDraftPr(jobId, input?.githubAccessToken)');
    expect(client).toContain("'/api/user/agent/swarm/run'");
    expect(client).toContain('expectedHeadSha: input.expectedHeadSha.trim()');
    expect(client).toContain('async listJobs(): Promise<SovereignAgentJobSnapshot[]>');
    expect(runtime).toContain('readSameOriginBackendUrl()');
  });

  it('binds the loaded repository snapshot to a real commit SHA', () => {
    const bridge = source('src/features/product/runtime/devChatWorkerBridge.ts');
    const builder = source('src/features/product/containers/BuilderContainer.tsx');

    expect(bridge).toContain('/commits/${encodeURIComponent(parsed.branch)}');
    expect(bridge).toContain("headSha: typeof commit.sha === 'string' ? commit.sha : undefined");
    expect(builder).toContain('expectedHeadSha: chatRepoSnapshot.headSha');
    expect(builder).toContain('githubAccessToken: githubTokenRef.current || undefined');
  });

  it('shows Rescue only for a real blocked or failed runtime state', () => {
    const app = source('src/App.tsx');

    expect(app).toContain("!rescueOpen && ['blocked', 'failed'].includes(agentJob.status)");
  });

  it('requires a concrete action preview before menu or slash Draft PR publication', () => {
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
