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

  it('preserves executable swarm, recovery, and publication behind the typed engine boundary while the Play root stays chat-only', () => {
    const app = source('src/App.tsx');
    const boundary = source('src/features/product/runtime/sovereignEngineBoundary.ts');
    const client = source('src/features/product/runtime/sovereignAgentClient.ts');
    const runtime = source('src/features/product/runtime/sovereignAgentRuntime.ts');

    expect(app).not.toContain("'START_REPOSITORY_EXECUTION'");
    expect(app).not.toContain("'CREATE_DRAFT_PR'");
    expect(app).not.toContain('executeSovereignEngineCommand');
    expect(boundary).toContain('await transport.startRepositoryExecution(command.payload.input)');
    expect(boundary).toContain('await transport.createDraftPr(command.payload.jobId, command.payload.githubAccessToken)');
    expect(boundary).toContain('await transport.getEvidenceAnchors(command.payload.jobId)');
    expect(boundary).toContain("'CANONICAL_JOB_SNAPSHOT_ACCEPTED'");
    expect(boundary).toContain("'CANONICAL_EVIDENCE_ANCHORS_ACCEPTED'");
    expect(client).toContain("'/api/user/agent/swarm/run'");
    expect(client).toContain('expectedHeadSha: input.expectedHeadSha.trim()');
    expect(client).toContain('async listJobs(): Promise<SovereignAgentJobSnapshot[]>');
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

  it('keeps Rescue available as a deferred module without mounting it into the Play release root', () => {
    const app = source('src/App.tsx');
    const rescue = source('src/features/rescue/RescuePanel.tsx');

    expect(app).not.toContain('RescuePanel');
    expect(app).not.toContain('Sovereign Rescue öffnen');
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
