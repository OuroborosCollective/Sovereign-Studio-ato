/**
 * Sovereign Capability Router Tests
 *
 * Test cases for Issue #502: Runtime: add Sovereign Capability Router
 *
 * Test cases required:
 * 1. Chatfrage → `worker-chat`
 * 2. Statusfrage → `local-runtime-answer`
 * 3. README-Änderung + GitHub ready + direct patch available → `direct-github-patch`
 * 4. README-Änderung + GitHub validating → blocked with `github_access_validating`
 * 5. README-Änderung + GitHub ready + OpenHands missing + no direct patch → blocked with `executor_unavailable`, not `github_access_missing`
 * 6. Große Codearbeit → `workspace-executor` oder `openhands`, nicht Direct Patch
 * 7. Draft PR → `draft-pr-runtime` nur bei GitHub ready
 * 8. Keine Entscheidung darf Token enthalten
 */

import { describe, it, expect } from 'vitest';
import {
  decideSovereignCapabilityRoute,
  classifyIntent,
  determineTaskComplexity,
  detectBlockers,
  buildCapabilityRouteActionEvent,
  requiresGitHubAccess,
  requiresExecutor,
  getRouteLabel,
  getBlockerExplanation,
  type CapabilityRouterInput,
  type CapabilityDecision,
} from './sovereignCapabilityRouter';
import type {
  IntentClassification,
  SovereignRoute,
  SovereignRouteBlocker,
  TaskComplexity,
} from './sovereignCapabilityTypes';

// ─────────────────────────────────────────────────────────────
// TEST HELPERS
// ─────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────
// TEST CASE 1: Chatfrage → worker-chat
// ─────────────────────────────────────────────────────────────

describe('Test Case 1: Chatfrage → worker-chat', () => {
  it('should route "Was bedeutet dieser Fehler?" to worker-chat', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Was bedeutet dieser Fehler?',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('worker-chat');
    expect(decision.capability).toBe('free_chat');
    expect(decision.allowed).toBe(true);
    expect(decision.blocker).toBeUndefined();
    expect(decision.nextAction).toBe('run_worker');
  });

  it('should classify "Was ist das?" as free_chat intent', () => {
    expect(classifyIntent('Was ist das?')).toBe('free_chat');
    expect(classifyIntent('Wie funktioniert das?')).toBe('free_chat');
    expect(classifyIntent('Erkläre mir das')).toBe('free_chat');
    expect(classifyIntent('hello, how are you?')).toBe('free_chat');
  });

  it('should not contain GitHub tokens in decision output', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Was bedeutet dieser Fehler?',
    };
    const decision = decideSovereignCapabilityRoute(input);

    // Decision should not expose GitHub tokens
    expect(JSON.stringify(decision)).not.toMatch(/gh[pousr]_[A-Za-z0-9]{20,}/);
    expect(JSON.stringify(decision)).not.toMatch(/[a-zA-Z0-9]{40,}/);
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 2: Statusfrage → local-runtime-answer
// ─────────────────────────────────────────────────────────────

describe('Test Case 2: Statusfrage → local-runtime-answer', () => {
  it('should route "Bist du fertig?" to local-runtime-answer', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Bist du fertig?',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('local-runtime-answer');
    expect(decision.capability).toBe('free_chat');
    expect(decision.allowed).toBe(true);
    expect(decision.nextAction).toBe('show_blocker');
  });

  it('should route "Arbeitet er schon?" to local-runtime-answer', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Arbeitet er schon?',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('local-runtime-answer');
  });

  it('should classify status questions correctly', () => {
    expect(classifyIntent('arbeitet er schon')).toBe('status_question');
    expect(classifyIntent('läuft das')).toBe('status_question');
    expect(classifyIntent('ist er fertig')).toBe('status_question');
    expect(classifyIntent('was macht er')).toBe('status_question');
    expect(classifyIntent('passiert gerade')).toBe('status_question');
  });

  it('should route status questions without calling external services', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Status?',
    };
    const decision = decideSovereignCapabilityRoute(input);

    // Status questions should be answered locally
    expect(decision.route).toBe('local-runtime-answer');
    expect(decision.nextAction).not.toBe('run_worker');
    expect(decision.nextAction).not.toBe('run_direct_patch');
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 3: README-Änderung + GitHub ready + direct patch available → direct-github-patch
// ─────────────────────────────────────────────────────────────

describe('Test Case 3: README-Änderung + GitHub ready + direct patch available → direct-github-patch', () => {
  it('should route README change to direct-github-patch when available', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Passe README an und füge 🐥 in den Titel ein',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('direct-github-patch');
    expect(decision.capability).toBe('direct_github_patch');
    expect(decision.allowed).toBe(true);
    expect(decision.nextAction).toBe('run_direct_patch');
  });

  it('should classify direct patch intents correctly', () => {
    expect(classifyIntent('passe readme an')).toBe('direct_patch');
    expect(classifyIntent('ändere die dokumentation')).toBe('direct_patch');
    expect(classifyIntent('zum changelog hinzufügen')).toBe('direct_patch');
    expect(classifyIntent('aktualisiere den titel')).toBe('direct_patch');
  });

  it('should not route complex tasks to direct patch', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Passe README an und implementiere Feature X',
    };
    const decision = decideSovereignCapabilityRoute(input);

    // Feature X is complex, should not go to direct patch
    expect(decision.route).not.toBe('direct-github-patch');
  });

  it('should determine simple complexity for direct patch tasks', () => {
    expect(determineTaskComplexity('direct_patch', 'passe readme an')).toBe('simple');
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 4: README-Änderung + GitHub validating → blocked with github_access_validating
// ─────────────────────────────────────────────────────────────

describe('Test Case 4: README-Änderung + GitHub validating → blocked with github_access_validating', () => {
  it('should block direct patch when GitHub is validating', () => {
    const input: CapabilityRouterInput = {
      ...GITHUB_VALIDATING_STATE,
      text: 'Passe README an',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('direct-github-patch');
    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('github_access_validating');
    expect(decision.nextAction).toBe('show_blocker');
  });

  it('should detect github_access_validating blocker', () => {
    const blockers = detectBlockers(GITHUB_VALIDATING_STATE);
    expect(blockers).toContain('github_access_validating');
  });

  it('should report validating state clearly', () => {
    const input: CapabilityRouterInput = {
      ...GITHUB_VALIDATING_STATE,
      text: 'Ändere die README Datei',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.reason).toContain('wird geprüft');
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 5: README-Änderung + GitHub ready + OpenHands missing + no direct patch → executor_unavailable
// ─────────────────────────────────────────────────────────────

describe('Test Case 5: README-Änderung + GitHub ready + OpenHands missing + no direct patch → executor_unavailable', () => {
  it('should block with executor_unavailable, not github_access_missing', () => {
    const input: CapabilityRouterInput = {
      text: 'Passe README an',
      repoReady: true,
      githubAccessState: 'ready', // GitHub IS ready
      openhandsReady: false,
      directGitHubPatchReady: false, // Direct patch NOT available
      workspaceReady: false,
      hasActiveWorkerBlocker: false,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('executor_unavailable');
    // Critical: must NOT be github_access_missing when GitHub is ready
    expect(decision.blocker).not.toBe('github_access_missing');
  });

  it('should suggest starting workspace when executor unavailable', () => {
    const input: CapabilityRouterInput = {
      text: 'Passe README an',
      repoReady: true,
      githubAccessState: 'ready',
      openhandsReady: false,
      directGitHubPatchReady: false,
      workspaceReady: false,
      hasActiveWorkerBlocker: false,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.nextAction).toBe('start_workspace');
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 6: Große Codearbeit → workspace-executor oder openhands
// ─────────────────────────────────────────────────────────────

describe('Test Case 6: Große Codearbeit → workspace-executor oder openhands', () => {
  it('should route complex code work to workspace-executor when available', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Implementiere Feature X und teste es',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('workspace-executor');
    expect(decision.capability).toBe('isolated_workspace');
    expect(decision.allowed).toBe(true);
    expect(decision.nextAction).toBe('start_workspace');
  });

  it('should route to openhands when workspace not ready', () => {
    const input: CapabilityRouterInput = {
      text: 'Baue Feature X ein',
      repoReady: true,
      githubAccessState: 'ready',
      openhandsReady: true,
      directGitHubPatchReady: false,
      workspaceReady: false, // Workspace not ready
      hasActiveWorkerBlocker: false,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('openhands');
    expect(decision.capability).toBe('code_patch_plan');
    expect(decision.allowed).toBe(true);
  });

  it('should not use direct patch for complex tasks', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Baue ein neues API-Backend mit Tests',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).not.toBe('direct-github-patch');
  });

  it('should classify complex tasks correctly', () => {
    expect(determineTaskComplexity('code_generation', 'baue ein backend')).toBe('complex');
    expect(determineTaskComplexity('code_generation', 'implementiere feature')).toBe('complex');
    expect(determineTaskComplexity('code_generation', 'refaktoriere den code')).toBe('complex');
  });

  it('should block complex work when no executor available', () => {
    const input: CapabilityRouterInput = {
      text: 'Baue Feature X ein und teste es',
      repoReady: true,
      githubAccessState: 'ready',
      openhandsReady: false,
      directGitHubPatchReady: false,
      workspaceReady: false, // No executor
      hasActiveWorkerBlocker: false,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('workspace_required');
    expect(decision.nextAction).toBe('start_workspace');
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 7: Draft PR → draft-pr-runtime nur bei GitHub ready
// ─────────────────────────────────────────────────────────────

describe('Test Case 7: Draft PR handling', () => {
  it('should block draft_pr when GitHub access is missing', () => {
    const input: CapabilityRouterInput = {
      text: 'Erstelle einen Draft PR',
      repoReady: true,
      githubAccessState: 'missing',
      openhandsReady: false,
      directGitHubPatchReady: false,
      workspaceReady: false,
      hasActiveWorkerBlocker: false,
      hasPackage: true,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('github_access_missing');
  });

  it('should block draft_pr when GitHub is validating', () => {
    const input: CapabilityRouterInput = {
      text: 'Erstelle einen Draft PR',
      repoReady: true,
      githubAccessState: 'validating',
      openhandsReady: false,
      directGitHubPatchReady: false,
      workspaceReady: false,
      hasActiveWorkerBlocker: false,
      hasPackage: true,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('github_access_validating');
  });

  it('should block draft_pr when no package generated', () => {
    const input: CapabilityRouterInput = {
      text: 'Erstelle einen Draft PR',
      repoReady: true,
      githubAccessState: 'ready',
      openhandsReady: true,
      directGitHubPatchReady: false,
      workspaceReady: true,
      hasActiveWorkerBlocker: false,
      hasPackage: false, // No package yet
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('unsupported_intent');
  });

  it('should route draft_pr to openhands when GitHub is ready and has package', () => {
    const input: CapabilityRouterInput = {
      text: 'Erstelle einen Draft PR',
      repoReady: true,
      githubAccessState: 'ready',
      openhandsReady: true,
      directGitHubPatchReady: false,
      workspaceReady: false,
      hasActiveWorkerBlocker: false,
      hasPackage: true,
      hasDraft: false,
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(true);
    expect(decision.route).toBe('openhands');
    expect(decision.capability).toBe('draft_pr');
  });
});

// ─────────────────────────────────────────────────────────────
// TEST CASE 8: Keine Entscheidung darf Token enthalten
// ─────────────────────────────────────────────────────────────

describe('Test Case 8: Security - No tokens in decisions', () => {
  it('should not contain GitHub tokens in decision output', () => {
    const decision = decideSovereignCapabilityRoute({
      text: 'Passe README an',
      repoReady: true,
      githubAccessState: 'ready',
      openhandsReady: true,
      directGitHubPatchReady: true,
      workspaceReady: true,
      hasActiveWorkerBlocker: false,
    });

    const decisionString = JSON.stringify(decision);
    // Should not contain token patterns
    expect(decisionString).not.toMatch(/gh[pousr]_[A-Za-z0-9]{20,}/);
    expect(decisionString).not.toMatch(/[a-zA-Z0-9]{40}/);
  });

  it('should not contain internal route tokens in user-facing output', () => {
    const decision = decideSovereignCapabilityRoute({
      text: 'Was ist das?',
      ...FULL_READY_STATE,
    });

    // Internal tokens should not leak into reason strings
    expect(decision.reason).not.toContain('_TOKEN');
    expect(decision.reason).not.toContain('PATTERN_');
  });

  it('should only use masked information in explanations', () => {
    const explanation = getBlockerExplanation('github_access_missing');

    // Should not contain actual token values
    expect(explanation).not.toMatch(/gh[pousr]_[A-Za-z0-9_]{10,}/);
    expect(explanation).toContain('GitHub-Zugang');
  });
});

// ─────────────────────────────────────────────────────────────
// ADDITIONAL TEST CASES
// ─────────────────────────────────────────────────────────────

describe('Repo loading', () => {
  it('should route GitHub URL to repo-load', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'https://github.com/owner/repo',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('repo-load');
    expect(decision.capability).toBe('repo_read');
  });

  it('should still route GitHub URL to repo-load even when repo is already loaded', () => {
    // User explicitly provided a GitHub URL - they want to load a new repo
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      repoReady: true,
      text: 'https://github.com/other/repo',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('repo-load');
  });
});

describe('Workflow watching', () => {
  it('should route workflow watch to worker-chat', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'Beobachte den Workflow-Status',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.route).toBe('worker-chat');
    expect(decision.capability).toBe('workflow_watch');
  });

  it('should block workflow watch when GitHub access missing', () => {
    const input: CapabilityRouterInput = {
      ...GITHUB_MISSING_STATE,
      text: 'Workflow-Status prüfen',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('github_access_missing');
  });
});

describe('Unknown intent', () => {
  it('should block unknown intent with ask_user action', () => {
    const input: CapabilityRouterInput = {
      ...FULL_READY_STATE,
      text: 'xyzabc123 nonsense',
    };
    const decision = decideSovereignCapabilityRoute(input);

    expect(decision.allowed).toBe(false);
    expect(decision.blocker).toBe('unsupported_intent');
    expect(decision.nextAction).toBe('ask_user');
  });

  it('should classify gibberish as unknown', () => {
    expect(classifyIntent('asdfghjkl')).toBe('unknown');
  });
});

describe('Helper functions', () => {
  describe('requiresGitHubAccess', () => {
    it('should return true for github-requiring routes', () => {
      const decision: CapabilityDecision = {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: 'Direct patch ready',
        nextAction: 'run_direct_patch',
      };
      expect(requiresGitHubAccess(decision)).toBe(true);
    });

    it('should return false for local routes', () => {
      const decision: CapabilityDecision = {
        route: 'local-runtime-answer',
        capability: 'free_chat',
        allowed: true,
        reason: 'Local answer',
        nextAction: 'show_blocker',
      };
      expect(requiresGitHubAccess(decision)).toBe(false);
    });
  });

  describe('requiresExecutor', () => {
    it('should return true for executor routes', () => {
      const decision: CapabilityDecision = {
        route: 'openhands',
        capability: 'code_patch_plan',
        allowed: true,
        reason: 'OpenHands ready',
        nextAction: 'start_openhands',
      };
      expect(requiresExecutor(decision)).toBe(true);
    });

    it('should return false for direct patch', () => {
      const decision: CapabilityDecision = {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: true,
        reason: 'Direct patch ready',
        nextAction: 'run_direct_patch',
      };
      expect(requiresExecutor(decision)).toBe(false);
    });
  });

  describe('getRouteLabel', () => {
    it('should return German labels for routes', () => {
      expect(getRouteLabel('worker-chat')).toBe('Chat Worker');
      expect(getRouteLabel('direct-github-patch')).toBe('Direct GitHub Patch');
      expect(getRouteLabel('openhands')).toBe('OpenHands');
    });
  });

  describe('getBlockerExplanation', () => {
    it('should return German explanations for blockers', () => {
      expect(getBlockerExplanation('repo_missing')).toContain('Repository');
      expect(getBlockerExplanation('github_access_missing')).toContain('GitHub');
      expect(getBlockerExplanation('executor_unavailable')).toContain('Executor');
    });
  });

  describe('detectBlockers', () => {
    it('should detect repo_missing blocker', () => {
      const blockers = detectBlockers({
        ...FULL_READY_STATE,
        repoReady: false,
      });
      expect(blockers).toContain('repo_missing');
    });

    it('should detect multiple blockers', () => {
      const blockers = detectBlockers({
        text: '',
        repoReady: false,
        githubAccessState: 'missing',
        openhandsReady: false,
        directGitHubPatchReady: false,
        workspaceReady: false,
        hasActiveWorkerBlocker: false,
      });
      expect(blockers).toContain('repo_missing');
      expect(blockers).toContain('github_access_missing');
      expect(blockers).toContain('executor_unavailable');
    });
  });
});

describe('Action event creation', () => {
  it('should create running event for allowed routes', () => {
    const decision: CapabilityDecision = {
      route: 'worker-chat',
      capability: 'free_chat',
      allowed: true,
      reason: 'Chat route selected',
      nextAction: 'run_worker',
    };

    const event = buildCapabilityRouteActionEvent(decision, 'trace-1', 0);

    expect(event.state).toBe('running');
    expect(event.route).toBe('worker-chat');
    expect(event.detail).toContain('Chat route');
  });

  it('should create blocked event for disallowed routes', () => {
    const decision: CapabilityDecision = {
      route: 'direct-github-patch',
      capability: 'direct_github_patch',
      allowed: false,
      reason: 'Direct patch blocked',
      blocker: 'github_access_missing',
      nextAction: 'validate_github_access',
    };

    const event = buildCapabilityRouteActionEvent(decision, 'trace-1', 0);

    expect(event.state).toBe('blocked');
    expect(event.route).toBe('direct-github-patch');
  });
});
