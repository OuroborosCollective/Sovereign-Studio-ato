import { describe, expect, it } from 'vitest';
import {
  canWorkspaceTouchPath,
  createSovereignWorkspaceScope,
  normalizeSovereignWorkspacePath,
  summarizeSovereignWorkspaceScope,
  validateSovereignWorkspaceScope,
} from './sovereignWorkspaceScopeRuntime';

function validScope() {
  return createSovereignWorkspaceScope({
    repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
    branch: 'main',
    allowedPaths: ['src/features/product/runtime/', 'tests/', 'README.md'],
    forbiddenPaths: ['src/secrets/', '.env.local'],
    draftPrOnly: true,
    githubWriteValidated: true,
    maxAction: 'draft_pr',
  });
}

describe('sovereignWorkspaceScopeRuntime', () => {
  it('creates a Draft-PR-only scope with default safety limits', () => {
    const scope = validScope();

    expect(scope.draftPrOnly).toBe(true);
    expect(scope.repoUrl).toBe('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
    expect(scope.maxRuntimeMs).toBeGreaterThanOrEqual(30_000);
    expect(validateSovereignWorkspaceScope(scope).allowed).toBe(true);
  });

  it('normalizes safe relative paths and rejects unsafe paths', () => {
    expect(normalizeSovereignWorkspacePath('./src/App.tsx')).toBe('src/App.tsx');
    expect(normalizeSovereignWorkspacePath('/etc/passwd')).toBeNull();
    expect(normalizeSovereignWorkspacePath('src/../secret.ts')).toBeNull();
    expect(normalizeSovereignWorkspacePath('')).toBeNull();
  });

  it('blocks write scopes without validated GitHub write access', () => {
    const scope = createSovereignWorkspaceScope({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      draftPrOnly: true,
      githubWriteValidated: false,
      maxAction: 'draft_pr',
    });

    const validation = validateSovereignWorkspaceScope(scope);
    expect(validation.allowed).toBe(false);
    expect(validation.blockers).toContain('Write workspace requires validated GitHub write access.');
    expect(validation.blockers).toContain('Draft PR workspace requires validated GitHub write access.');
  });

  it('allows read-only scope without GitHub write validation', () => {
    const scope = createSovereignWorkspaceScope({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      draftPrOnly: true,
      githubWriteValidated: false,
      maxAction: 'read_only',
    });

    expect(validateSovereignWorkspaceScope(scope).allowed).toBe(true);
  });

  it('enforces allowed and forbidden paths with forbidden winning', () => {
    const scope = validScope();

    expect(canWorkspaceTouchPath(scope, 'src/features/product/runtime/example.ts').allowed).toBe(true);
    expect(canWorkspaceTouchPath(scope, 'src/secrets/token.ts').allowed).toBe(false);
    expect(canWorkspaceTouchPath(scope, 'android/app/build/output.apk').allowed).toBe(false);
    expect(canWorkspaceTouchPath(scope, 'package.json').allowed).toBe(false);
  });

  it('blocks secret-like text in scope values', () => {
    const scope = createSovereignWorkspaceScope({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      branch: ['ghp', 'abcdefghijklmnopqrstuvwxyz1234567890'].join('_'),
      draftPrOnly: true,
      githubWriteValidated: true,
      maxAction: 'draft_pr',
    });

    expect(validateSovereignWorkspaceScope(scope).blockers).toContain('Workspace scope contains secret-like text.');
  });

  it('summarizes scope without creating execution truth', () => {
    const summary = summarizeSovereignWorkspaceScope(validScope());

    expect(summary).toContain('Repo: OuroborosCollective/Sovereign-Studio-ato');
    expect(summary).toContain('Draft PR only: yes');
  });
});
