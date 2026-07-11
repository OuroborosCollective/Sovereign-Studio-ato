/**
 * Sovereign Workspace Policy Tests
 *
 * Tests for workspace policy rules and gates.
 * Covers acceptance criteria from Issue #503.
 */

import { describe, it, expect } from 'vitest';
import {
  evaluateTaskComplexity,
  shouldCreateWorkspace,
  validateChangedFiles,
  evaluateWorkspacePolicy,
  createRepoGate,
  createExecutorGate,
  createPathValidationGate,
  createWorkspaceRequirementGate,
  DEFAULT_POLICY_GATES,
} from './sovereignWorkspacePolicy';
import type { WorkspaceGateContext } from './sovereignWorkspaceTypes';

describe('evaluateTaskComplexity', () => {
  it('should not require workspace for simple questions', () => {
    const result = evaluateTaskComplexity('Was ist Sovereign Studio?');
    expect(result.requiresWorkspace).toBe(false);
    expect(result.reason).toContain('Simple question');
  });

  it('should not require workspace for status queries', () => {
    const result = evaluateTaskComplexity('Status der Pipeline?');
    expect(result.requiresWorkspace).toBe(false);
    expect(result.reason).toContain('Simple question');
  });

  it('should not require workspace for readme-only patches', () => {
    const result = evaluateTaskComplexity('Update the README with new features', ['README.md']);
    expect(result.requiresWorkspace).toBe(false);
    expect(result.suggestedPurpose).toBe('patch');
  });

  it('should not require workspace for docs-only patches', () => {
    const result = evaluateTaskComplexity('Update documentation', ['docs/guide.md']);
    expect(result.requiresWorkspace).toBe(false);
    expect(result.suggestedPurpose).toBe('patch');
  });

  it('should require workspace for multi-file changes', () => {
    const result = evaluateTaskComplexity('Update multiple files', ['src/a.ts', 'src/b.ts']);
    expect(result.requiresWorkspace).toBe(true);
    expect(result.suggestedPurpose).toBe('patch');
  });

  it('should require workspace for source code changes', () => {
    const result = evaluateTaskComplexity('Fix the bug in the auth module', ['src/auth/login.ts']);
    expect(result.requiresWorkspace).toBe(true);
    // Fix matches complex patterns
    expect(result.reason).toContain('workspace');
  });

  it('should require workspace for Android changes', () => {
    const result = evaluateTaskComplexity('Update Android manifest', ['android/app/src/main/AndroidManifest.xml']);
    expect(result.requiresWorkspace).toBe(true);
    // Android changes require workspace
    expect(result.reason).toContain('workspace');
  });

  it('should require workspace for test tasks', () => {
    const result = evaluateTaskComplexity('Run tests and fix failures');
    expect(result.requiresWorkspace).toBe(true);
    expect(result.suggestedPurpose).toBe('test');
  });

  it('should require workspace for draft PR tasks', () => {
    const result = evaluateTaskComplexity('Create a draft PR with the changes');
    expect(result.requiresWorkspace).toBe(true);
    expect(result.suggestedPurpose).toBe('draft_pr');
  });

  it('should require workspace for repair tasks', () => {
    const result = evaluateTaskComplexity('Fix the error in the build process');
    expect(result.requiresWorkspace).toBe(true);
    expect(result.suggestedPurpose).toBe('repair');
  });
});

describe('shouldCreateWorkspace', () => {
  it('should not create workspace for chat question without repo', () => {
    const result = shouldCreateWorkspace(undefined, undefined, 'Was ist Sovereign?');
    expect(result.allowed).toBe(false);
    // The first evidence-backed blocker is the missing repository.
    expect(result.blocker).toBe('repo_missing');
  });

  it('should not create workspace for readme patch when no executor available', () => {
    const result = shouldCreateWorkspace(
      'https://github.com/test/repo',
      'main',
      'Update README',
      ['README.md'],
      false
    );
    // Direct patch route is allowed even without executor
    expect(result.allowed).toBe(false);
    expect(result.rules.find((r) => r.id === 'workspace-required')?.passed).toBe(false);
  });

  it('should block workspace when required but no executor available', () => {
    const result = shouldCreateWorkspace(
      'https://github.com/test/repo',
      'main',
      'Fix bug in auth module',
      ['src/auth/login.ts'],
      false
    );
    expect(result.allowed).toBe(false);
    // The workspace requirement gate identifies the precise missing capability first.
    expect(result.blocker).toBe('workspace_required');
  });

  it('should allow workspace when required and executor available', () => {
    const result = shouldCreateWorkspace(
      'https://github.com/test/repo',
      'main',
      'Fix bug in auth module',
      ['src/auth/login.ts'],
      true
    );
    expect(result.allowed).toBe(true);
    expect(result.rules.every((r) => r.passed)).toBe(true);
  });

  it('should block workspace without repo URL', () => {
    const result = shouldCreateWorkspace(undefined, 'main', 'Fix bug', ['src/a.ts'], true);
    expect(result.allowed).toBe(false);
    expect(result.rules.find((r) => r.id === 'repo-available')?.passed).toBe(false);
  });

  it('should block workspace with invalid repo URL', () => {
    const result = shouldCreateWorkspace(
      'https://gitlab.com/test/repo',
      'main',
      'Fix bug',
      ['src/a.ts'],
      true
    );
    expect(result.allowed).toBe(false);
    const repoRule = result.rules.find((r) => r.id === 'repo-available');
    expect(repoRule?.passed).toBe(false);
  });
});

describe('validateChangedFiles', () => {
  it('should validate files within allowed paths', () => {
    const result = validateChangedFiles(
      ['src/auth/login.ts', 'src/auth/logout.ts'],
      ['src/'],
      []
    );
    expect(result.valid).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  it('should detect files outside allowed paths', () => {
    const result = validateChangedFiles(
      ['src/auth/login.ts', 'android/app/src/main/Activity.java'],
      ['src/'],
      []
    );
    expect(result.valid).toBe(false);
    expect(result.violations).toContain(
      'android/app/src/main/Activity.java is not within allowed paths'
    );
  });

  it('should detect forbidden paths', () => {
    const result = validateChangedFiles(
      ['src/main.ts', '.env'],
      [],
      ['.env', 'node_modules/']
    );
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('.env matches forbidden path .env');
  });

  it('should detect forbidden subdirectories', () => {
    const result = validateChangedFiles(
      ['src/main.ts', 'node_modules/express/index.js'],
      ['src/'],
      ['node_modules/']
    );
    expect(result.valid).toBe(false);
    expect(result.violations).toContain(
      'node_modules/express/index.js matches forbidden path node_modules/'
    );
  });

  it('should allow empty file list', () => {
    const result = validateChangedFiles([], ['src/'], []);
    expect(result.valid).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  it('should require allowed paths if specified', () => {
    const result = validateChangedFiles(['README.md'], ['src/'], []);
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('README.md is not within allowed paths');
  });
});

describe('Workspace Gates', () => {
  const baseContext: WorkspaceGateContext = {
    repoUrl: 'https://github.com/test/repo',
    baseBranch: 'main',
    mission: 'Test mission',
    targetPaths: ['src/main.ts'],
    requiresWorkspace: true,
    isSimpleQuestion: false,
    isReadOnlyAnalysis: false,
    isSmallDocPatch: false,
    hasWorkspaceExecutor: true,
  };

  describe('createRepoGate', () => {
    it('should pass with valid GitHub URL', () => {
      const gate = createRepoGate();
      const result = gate.check(baseContext);
      expect(result.passed).toBe(true);
    });

    it('should fail without repo URL', () => {
      const gate = createRepoGate();
      const result = gate.check({ ...baseContext, repoUrl: undefined });
      expect(result.passed).toBe(false);
      expect(result.blocker).toBe('repo_missing');
    });

    it('should fail with non-GitHub URL', () => {
      const gate = createRepoGate();
      const result = gate.check({ ...baseContext, repoUrl: 'https://gitlab.com/test/repo' });
      expect(result.passed).toBe(false);
      expect(result.blocker).toBe('invalid_repo_url');
    });
  });

  describe('createExecutorGate', () => {
    it('should pass when executor is available', () => {
      const gate = createExecutorGate();
      const result = gate.check(baseContext);
      expect(result.passed).toBe(true);
    });

    it('should fail when executor is not available', () => {
      const gate = createExecutorGate();
      const result = gate.check({ ...baseContext, hasWorkspaceExecutor: false });
      expect(result.passed).toBe(false);
      expect(result.blocker).toBe('executor_unavailable');
    });
  });

  describe('createPathValidationGate', () => {
    it('should pass with valid paths', () => {
      const gate = createPathValidationGate();
      const result = gate.check(baseContext);
      expect(result.passed).toBe(true);
    });

    it('should pass with no target paths', () => {
      const gate = createPathValidationGate();
      const result = gate.check({ ...baseContext, targetPaths: [] });
      expect(result.passed).toBe(true);
    });

    it('should fail with forbidden paths', () => {
      const gate = createPathValidationGate();
      const result = gate.check({ ...baseContext, targetPaths: ['.env'] });
      expect(result.passed).toBe(false);
      expect(result.blocker).toBe('forbidden_path');
    });
  });

  describe('createWorkspaceRequirementGate', () => {
    it('should not require workspace for simple questions', () => {
      const gate = createWorkspaceRequirementGate();
      const result = gate.check({ ...baseContext, isSimpleQuestion: true, requiresWorkspace: false });
      expect(result.passed).toBe(false);
      expect(result.nextAction).toBe('direct_patch');
    });

    it('should allow workspace for complex tasks with executor', () => {
      const gate = createWorkspaceRequirementGate();
      const result = gate.check({ ...baseContext, requiresWorkspace: true });
      expect(result.passed).toBe(true);
      expect(result.nextAction).toBe('start_workspace');
    });

    it('should block workspace for complex tasks without executor', () => {
      const gate = createWorkspaceRequirementGate();
      const result = gate.check({
        ...baseContext,
        requiresWorkspace: true,
        hasWorkspaceExecutor: false,
      });
      expect(result.passed).toBe(false);
      expect(result.blocker).toBe('workspace_required');
    });

    it('should recommend direct_patch for small doc patches', () => {
      const gate = createWorkspaceRequirementGate();
      const result = gate.check({ ...baseContext, isSmallDocPatch: true, requiresWorkspace: false });
      expect(result.passed).toBe(false);
      expect(result.nextAction).toBe('direct_patch');
    });
  });
});

describe('DEFAULT_POLICY_GATES', () => {
  it('should have all required gates in order', () => {
    const gateIds = DEFAULT_POLICY_GATES.map((g) => g.name);
    expect(gateIds).toContain('repo-available');
    expect(gateIds).toContain('path-validation');
    expect(gateIds).toContain('workspace-required');
    expect(gateIds).toContain('executor-available');
    expect(gateIds).toContain('draft-pr-validation');
  });
});

describe('evaluateWorkspacePolicy', () => {
  it('should aggregate all gate results', () => {
    const context: WorkspaceGateContext = {
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Fix bug in source',
      targetPaths: ['src/main.ts'],
      requiresWorkspace: true,
      isSimpleQuestion: false,
      isReadOnlyAnalysis: false,
      isSmallDocPatch: false,
      hasWorkspaceExecutor: true,
    };

    const result = evaluateWorkspacePolicy(context);
    expect(result.rules.length).toBe(DEFAULT_POLICY_GATES.length);
    expect(result.allowed).toBe(true);
  });

  it('should fail if any gate fails', () => {
    const context: WorkspaceGateContext = {
      repoUrl: 'https://gitlab.com/test/repo', // Invalid
      baseBranch: 'main',
      mission: 'Fix bug in source',
      targetPaths: ['src/main.ts'],
      requiresWorkspace: true,
      isSimpleQuestion: false,
      isReadOnlyAnalysis: false,
      isSmallDocPatch: false,
      hasWorkspaceExecutor: true,
    };

    const result = evaluateWorkspacePolicy(context);
    expect(result.allowed).toBe(false);
    expect(result.rules.some((r) => !r.passed)).toBe(true);
  });
});
