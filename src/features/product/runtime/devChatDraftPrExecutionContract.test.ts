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

  it('keeps mission execution and Draft-PR publication on the current Play Release job identity', () => {
    const app = source('src/App.tsx');
    const release = source('src/features/release/PlayReleaseChat.tsx');
    const client = source('src/features/product/runtime/sovereignAgentClient.ts');
    const runtime = source('src/features/product/runtime/sovereignAgentRuntime.ts');

    expect(app).toContain('PlayReleaseChat');
    expect(app).toContain('data-layout="chat-first-agent-zero-background"');
    expect(app).toContain('data-primary-surface="play-release-chat"');
    expect(app).toContain('data-truth-scope="current-chat-session-only"');
    expect(app).not.toContain('RESTORE_LATEST_JOB');
    expect(app).not.toContain('BuilderContainer');

    expect(release).toContain('createSovereignAgentClient');
    expect(release).toContain('agentClient.startRepositoryExecution');
    expect(release).toContain('agentClient.getJob(snapshot.jobId)');
    expect(release).toContain('agentClient.prepareDraftPr(snapshot.jobId)');
    expect(release).toContain('agentClient.createDraftPr(snapshot.jobId');
    expect(release).toContain('created.draftPrCreate.readbackHeadSha');
    expect(release).not.toContain('listJobs(');
    expect(release).not.toContain('RESTORE_LATEST_JOB');

    expect(client).toContain("'/api/user/agent/swarm/run'");
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

  it('keeps Rescue available through a current-session exact-job bridge', () => {
    const app = source('src/App.tsx');
    const overlay = source('src/features/rescue/SovereignRescueOverlay.tsx');
    const rescue = source('src/features/rescue/RescuePanel.tsx');

    expect(app).toContain("import { SovereignRescueOverlay } from './features/rescue/SovereignRescueOverlay';");
    expect(app).toContain('<SovereignRescueOverlay />');
    expect(overlay).toContain('aria-label="Sovereign Rescue öffnen"');
    expect(overlay).toContain('<RescuePanel');
    expect(overlay).toContain('client.getJob(jobId)');
    expect(overlay).toContain('snapshot.jobId !== jobId');
    expect(overlay).toContain('client.getJob(job.jobId)');
    expect(overlay).toContain('client.prepareDraftPr(current.jobId)');
    expect(overlay).toContain('client.createDraftPr(current.jobId)');
    expect(overlay).toContain('created.draftPrCreate.readbackHeadSha');
    expect(overlay).not.toContain('listJobs(');
    expect(overlay).not.toContain('RESTORE_LATEST_JOB');
    expect(rescue).toContain('RescuePanel');
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
