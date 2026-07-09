import { describe, expect, it } from 'vitest';
import {
  buildCapabilityRouteActionEvent,
  classifyIntent,
  decideSovereignCapabilityRoute,
  detectBlockers,
  determineTaskComplexity,
  getBlockerExplanation,
  getRouteLabel,
  requiresExecutor,
  requiresGitHubAccess,
  type CapabilityRouterInput,
} from './sovereignCapabilityRouter';

const FULL_READY_STATE: CapabilityRouterInput = {
  text: '',
  repoReady: true,
  githubAccessState: 'ready',
  openhandsReady: true,
  directGitHubPatchReady: true,
  workspaceReady: true,
  hasActiveWorkerBlocker: false,
};

const GITHUB_MISSING_STATE: CapabilityRouterInput = {
  text: '',
  repoReady: true,
  githubAccessState: 'missing',
  openhandsReady: false,
  directGitHubPatchReady: false,
  workspaceReady: false,
  hasActiveWorkerBlocker: false,
};

const GITHUB_VALIDATING_STATE: CapabilityRouterInput = {
  text: '',
  repoReady: true,
  githubAccessState: 'validating',
  openhandsReady: true,
  directGitHubPatchReady: true,
  workspaceReady: true,
  hasActiveWorkerBlocker: false,
};

describe('Sovereign Capability Router', () => {
  describe('chat and status routing', () => {
    it('routes free chat to worker-chat', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Was bedeutet dieser Fehler?',
      });

      expect(decision.route).toBe('worker-chat');
      expect(decision.capability).toBe('free_chat');
      expect(decision.allowed).toBe(true);
      expect(decision.nextAction).toBe('run_worker');
    });

    it('routes status questions to local runtime answer', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Bist du fertig?',
      });

      expect(decision.route).toBe('local-runtime-answer');
      expect(decision.isTerminal).toBe(true);
      expect(decision.nextAction).toBe('answer_locally');
    });

    it('records local runtime answers as checked capability, not blocker handling', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Was ist der Status?',
      });
      const event = buildCapabilityRouteActionEvent(decision, 'trace-local', 0);

      expect(event.kind).toBe('capability_checked');
      expect(event.route).toBe('local-runtime-answer');
      expect(event.label).toBe('Lokale Runtime-Antwort vorbereitet');
      expect(event.state).toBe('done');
      expect(decision.nextAction).toBe('answer_locally');
    });

    it('classifies common intents', () => {
      expect(classifyIntent('Was ist das?')).toBe('free_chat');
      expect(classifyIntent('arbeitet er schon')).toBe('status_question');
      expect(classifyIntent('https://github.com/owner/repo')).toBe('load_repo');
    });
  });

  describe('direct patch routing', () => {
    it('routes simple README changes to direct GitHub patch when available', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Passe README an und füge 🐥 in den Titel ein',
      });

      expect(decision.route).toBe('direct-github-patch');
      expect(decision.allowed).toBe(true);
      expect(decision.nextAction).toBe('run_direct_patch');
    });

    it('blocks direct patch while GitHub is validating', () => {
      const decision = decideSovereignCapabilityRoute({
        ...GITHUB_VALIDATING_STATE,
        text: 'Passe README an',
      });

      expect(decision.allowed).toBe(false);
      expect(decision.blocker).toBe('github_access_validating');
      expect(decision.nextAction).toBe('show_blocker');
    });

    it('blocks direct patch with executor_unavailable when GitHub is already ready but no patch route exists', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Passe README an',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: false,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
      });

      expect(decision.allowed).toBe(false);
      expect(decision.blocker).toBe('executor_unavailable');
      expect(decision.blocker).not.toBe('github_access_missing');
      expect(decision.nextAction).toBe('start_workspace');
    });
  });

  describe('code generation routing', () => {
    it('routes complex code work to workspace when workspace is available', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Implementiere Feature X und teste es',
      });

      expect(decision.route).toBe('workspace-executor');
      expect(decision.capability).toBe('isolated_workspace');
      expect(decision.allowed).toBe(true);
      expect(decision.nextAction).toBe('start_workspace');
    });

    it('routes explicit Draft-PR execution to openhands when explicitly requested', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Bitte mit OpenHands einen Draft PR erstellen.',
        repoReady: true,
        githubAccessState: 'missing',
        openhandsReady: true,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
      });

      expect(decision.route).toBe('openhands');
      expect(decision.capability).toBe('draft_pr');
      expect(decision.allowed).toBe(true);
      expect(decision.nextAction).toBe('start_openhands');
    });

    it('routes complex code work to workspace-executor when available', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Baue Feature X ein',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: true,
        directGitHubPatchReady: false,
        workspaceReady: true,
        hasActiveWorkerBlocker: false,
      });

      expect(decision.route).toBe('workspace-executor');
      expect(decision.capability).toBe('isolated_workspace');
      expect(decision.allowed).toBe(true);
    });

    it('blocks complex code work with workspace_required when no executor exists', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Baue Feature X ein und teste es',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: false,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
      });

      expect(decision.allowed).toBe(false);
      expect(decision.blocker).toBe('workspace_required');
      expect(decision.nextAction).toBe('start_workspace');
    });

    it('does not dead-end medium code work when package is missing', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Fixe den kleinen Button Bug',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: false,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
        hasPackage: false,
      });

      expect(decision.allowed).toBe(true);
      expect(decision.route).toBe('code-llm');
      expect(decision.blocker).toBe('package_required');
      expect(decision.nextAction).toBe('generate_patch_package');
      expect(decision.reason).toContain('Patch-Paket');
    });

    it('runs code-llm when a package already exists', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Fixe den kleinen Button Bug',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: false,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
        hasPackage: true,
      });

      expect(decision.allowed).toBe(true);
      expect(decision.route).toBe('code-llm');
      expect(decision.nextAction).toBe('run_worker');
    });
  });

  describe('draft PR package gate', () => {
    it('keeps draft PR without package recoverable using package_required instead of unsupported_intent', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Erstelle einen Draft PR',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: true,
        directGitHubPatchReady: false,
        workspaceReady: true,
        hasActiveWorkerBlocker: false,
        hasPackage: false,
      });

      expect(decision.allowed).toBe(true);
      expect(decision.route).toBe('draft-pr-runtime');
      expect(decision.blocker).toBe('package_required');
      expect(decision.nextAction).toBe('generate_patch_package');
      expect(decision.blocker).not.toBe('unsupported_intent');
      expect(decision.nextAction).not.toBe('ask_user');
    });

    it('blocks draft PR when GitHub is missing after package exists', () => {
      const decision = decideSovereignCapabilityRoute({
        ...GITHUB_MISSING_STATE,
        text: 'Erstelle einen Draft PR',
        hasPackage: true,
      });

      expect(decision.allowed).toBe(false);
      expect(decision.blocker).toBe('github_access_missing');
    });

    it('routes draft PR to workspace-executor when workspace is ready', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Erstelle einen Draft PR',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: true,
        directGitHubPatchReady: false,
        workspaceReady: true,
        hasActiveWorkerBlocker: false,
        hasPackage: true,
      });

      expect(decision.allowed).toBe(true);
      expect(decision.route).toBe('workspace-executor');
      expect(decision.capability).toBe('draft_pr');
    });

    it('blocks draft PR when no executor is available', () => {
      const decision = decideSovereignCapabilityRoute({
        text: 'Erstelle einen Draft PR',
        repoReady: true,
        githubAccessState: 'ready',
        openhandsReady: false,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
        hasPackage: true,
      });

      expect(decision.allowed).toBe(false);
      expect(decision.blocker).toBe('executor_unavailable');
    });
  });

  describe('workflow and repo routing', () => {
    it('routes workflow watch to worker-chat with workflow capability', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Beobachte den Workflow-Status',
      });

      expect(decision.route).toBe('worker-chat');
      expect(decision.capability).toBe('workflow_watch');
    });

    it('blocks workflow watch when GitHub access is missing', () => {
      const decision = decideSovereignCapabilityRoute({
        ...GITHUB_MISSING_STATE,
        text: 'Workflow-Status prüfen',
      });

      expect(decision.allowed).toBe(false);
      expect(decision.blocker).toBe('github_access_missing');
    });
  });

  describe('helpers and security', () => {
    it('detects blockers from runtime state', () => {
      expect(detectBlockers(GITHUB_VALIDATING_STATE)).toContain('github_access_validating');
      expect(detectBlockers(GITHUB_MISSING_STATE)).toContain('github_access_missing');
    });

    it('classifies complexity', () => {
      expect(determineTaskComplexity('direct_patch', 'passe readme an')).toBe('simple');
      expect(determineTaskComplexity('code_generation', 'baue ein backend')).toBe('complex');
      expect(determineTaskComplexity('code_generation', 'fixe button')).toBe('medium');
    });

    it('builds action events from decisions', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Was ist das?',
      });
      const event = buildCapabilityRouteActionEvent(decision, 'trace', 0);
      expect(event.kind).toBe('route_selected');
      expect(event.state).toBe('running');
    });

    it('keeps package_required visible in blocker explanation', () => {
      expect(getBlockerExplanation('package_required')).toContain('Patch-Paket');
    });

    it('exports route labels and executor checks', () => {
      expect(getRouteLabel('draft-pr-runtime')).toBe('Draft PR');
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Implementiere Feature X und teste es',
      });
      expect(requiresExecutor(decision)).toBe(true);
      expect(requiresGitHubAccess(decision)).toBe(true);
    });

    it('does not leak GitHub tokens into decisions', () => {
      const decision = decideSovereignCapabilityRoute({
        ...FULL_READY_STATE,
        text: 'Passe README an',
      });
      const serialized = JSON.stringify(decision);
      expect(serialized).not.toMatch(/gh[pousr]_[A-Za-z0-9]{20,}/);
      expect(serialized).not.toMatch(/github_pat_[A-Za-z0-9_]{20,}/);
      expect(serialized).not.toMatch(/[a-zA-Z0-9]{40}/);
    });
  });
});
