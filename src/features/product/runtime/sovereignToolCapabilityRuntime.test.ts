import { describe, expect, it } from 'vitest';
import {
  buildSovereignToolCapabilityRegistry,
  getSovereignToolCapability,
  isGitHubWriteReady,
  summarizeBlockedCapabilities,
} from './sovereignToolCapabilityRuntime';

function readyInput() {
  return {
    repoReady: true,
    githubAccessState: 'ready' as const,
    githubTokenPresent: true,
    directPatchSupported: true,
    openhandsConfigured: true,
    workerAvailable: true,
    workspaceConfigured: true,
    draftPrSupported: true,
    activeExecutorStatus: 'idle' as const,
  };
}

describe('sovereignToolCapabilityRuntime', () => {
  it('marks write routes ready only from runtime capabilities', () => {
    const registry = buildSovereignToolCapabilityRegistry(readyInput());

    expect(registry.repo.status).toBe('ready');
    expect(registry.githubWrite.status).toBe('ready');
    expect(registry.directPatch.canStart).toBe(true);
    expect(registry.openhands.canStart).toBe(true);
    expect(registry.workspace.canStart).toBe(true);
    expect(registry.draftPr.canStart).toBe(true);
  });

  it('does not treat token presence alone as GitHub write readiness', () => {
    expect(isGitHubWriteReady({ githubAccessState: 'missing', githubTokenPresent: true })).toBe(false);
    expect(isGitHubWriteReady({ githubAccessState: 'ready', githubTokenPresent: false })).toBe(false);
    expect(isGitHubWriteReady({ githubAccessState: 'ready', githubTokenPresent: true })).toBe(true);
  });

  it('blocks Direct Patch and OpenHands without validated GitHub write access', () => {
    const registry = buildSovereignToolCapabilityRegistry({
      ...readyInput(),
      githubAccessState: 'missing',
      githubTokenPresent: false,
    });

    expect(registry.githubWrite.status).toBe('blocked');
    expect(registry.githubWrite.nextAction).toBe('request_github_access');
    expect(registry.directPatch.canStart).toBe(false);
    expect(registry.directPatch.blocker).toBe('github_access_missing');
    expect(registry.openhands.canStart).toBe(false);
    expect(registry.openhands.blocker).toBe('github_access_missing');
  });

  it('blocks parallel executors while another executor is active', () => {
    const registry = buildSovereignToolCapabilityRegistry({
      ...readyInput(),
      activeExecutorStatus: 'running',
    });

    expect(registry.directPatch.canStart).toBe(false);
    expect(registry.directPatch.blocker).toBe('executor_active');
    expect(registry.openhands.canStart).toBe(false);
    expect(registry.openhands.blocker).toBe('executor_active');
    expect(registry.workspace.canStart).toBe(false);
    expect(registry.workspace.blocker).toBe('executor_active');
  });

  it('keeps Worker Chat independent from write access', () => {
    const registry = buildSovereignToolCapabilityRegistry({
      ...readyInput(),
      repoReady: false,
      githubAccessState: 'missing',
      githubTokenPresent: false,
    });

    expect(registry.workerChat.canStart).toBe(true);
    expect(registry.workerChat.reason).toContain('keine Schreibwahrheit');
    expect(getSovereignToolCapability(registry, 'worker_chat')).toBe(registry.workerChat);
  });

  it('summarizes non-ready capabilities for compact UI display', () => {
    const registry = buildSovereignToolCapabilityRegistry({
      ...readyInput(),
      repoReady: false,
      directPatchSupported: false,
      openhandsConfigured: false,
      workspaceConfigured: false,
      draftPrSupported: false,
    });

    const blocked = summarizeBlockedCapabilities(registry).map((item) => item.id);
    expect(blocked).toContain('repo');
    expect(blocked).toContain('direct_patch');
    expect(blocked).toContain('openhands');
  });
});
