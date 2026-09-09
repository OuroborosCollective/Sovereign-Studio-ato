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
      "stringValue(signal.prStateVerified) === 'open'",
      'signal.draftVerified === true',
    ]) expect(client).toContain(strictReadback);
  });

  it('turns an explicit GitHub repository URL into the backend repository-execution contract instead of free conversation mode', () => {
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    const backend = source('backend/agent_runtime/cognitive_swarm_routes.py');

    expect(adapter).toContain('extractGitHubRepositoryUrl(mission)');
    expect(adapter).toContain("intentMode: 'repository_execution'");
    expect(adapter).toContain('repositoryUrl,');
    expect(adapter).toContain("repositoryBranch: 'main'");
    expect(backend).toContain('if free_profile and selected == "auto":');
    expect(backend).toContain('return "conversation"');
    expect(backend).toContain('mission_intent.mode == "repository_execution"');
    expect(backend).toContain('normalized_repository_url');
  });

  it('projects real pending owner approvals and writes decisions through the canonical approval endpoint', () => {
    const adapter = source('src/features/control-surface-vnext/adapter/production-adapter.ts');
    const ownerHook = source('src/features/control-surface-vnext/hooks/useOwnerInteraction.ts');
    const backend = source('scripts/sovereign-backend/controller_board.py');

    expect(adapter).toContain("'/api/controller/approvals'");
    expect(adapter).toContain('/api/controller/approvals/${encodeURIComponent(interactionId)}/decision');
    expect(adapter).toContain("options: approval.requiresProtectedOwnerInput ? undefined : ['approve', 'reject']");
    expect(adapter).toContain("case 'READY_FOR_DRAFT_PR': return 'READY_TO_PUBLISH'");
    expect(adapter).toContain("runPhase === 'AWAITING_OWNER_INPUT'");
    expect(ownerHook).toContain("invalidateQueries({ queryKey: ['sovereign-vnext-job', jobId] })");
    expect(backend).toContain('@app.route("/api/controller/approvals/<approval_id>/decision", methods=["POST"])');
    expect(backend).toContain('draft_pr_approval = approved and approval_kind == "draft_pr_readiness"');
  });

  it('allows a backend guest session to upgrade directly to authenticated execution without token storage', () => {
    const auth = source('src/features/control-surface-vnext/components/Auth/OperatorAuthModal.tsx');
    expect(auth).toContain('user && !user.isGuest');
    expect(auth).toContain('GUEST SESSION ACTIVE');
    expect(auth).toContain('AUTHENTICATE WITH ACCOUNT KEY');
    expect(auth).toContain('HTTP-ONLY COOKIE · NO FRONTEND TOKEN STORAGE');
    expect(auth).not.toContain('localStorage');
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

  it('mounts exactly one responsive product tree instead of CSS-hiding duplicate desktop/mobile controls', () => {
    const surface = source('src/features/control-surface-vnext/App.tsx');
    const modal = source('src/features/control-surface-vnext/components/Modal.tsx');

    expect(surface).toContain('function useDesktopLayout()');
    expect(surface).toContain('const isDesktopLayout = useDesktopLayout()');
    expect(surface).toContain('isDesktopLayout ? (');
    expect(surface).toContain('data-testid="vnext-desktop-layout"');
    expect(surface).toContain('data-testid="vnext-mobile-layout"');
    expect(surface).not.toContain('hidden md:flex w-full h-full');
    expect(surface).not.toContain('md:hidden flex flex-col w-full h-full');
    expect(modal).toContain('role="dialog"');
    expect(modal).toContain('aria-modal="true"');
    expect(modal).toContain('aria-label={title}');
  });

  it('keeps the protected five-run evidence lane on vNext instead of historical side-menu or PAT choreography', () => {
    const live = source('tests/e2e/five-draft-pr-paths.spec.ts');
    for (const required of [
      'sovereign-control-surface-vnext',
      'operator-auth-btn',
      'vnext-account-key',
      'PERSISTED RUN ACCEPTED',
      'vnext-prepare-draft-pr',
      'vnext-draft-pr-consent',
      'vnext-create-draft-pr',
      'GITHUB READBACK VERIFIED',
      'result.body.head.sha).toBe(ui.readbackHeadSha)',
      'verifyReadmeAtHead',
    ]) expect(live).toContain(required);

    for (const retired of [
      'sovereign-side-menu',
      'github-pat-input',
      'Tool Launcher öffnen',
      'Repo Inspector öffnen',
      "submitComposer(page, '/pr')",
    ]) expect(live).not.toContain(retired);
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
