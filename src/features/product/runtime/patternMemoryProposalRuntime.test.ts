/**
 * Unit tests for patternMemoryProposalRuntime — Issue #447
 */

import { describe, expect, it } from 'vitest';
import {
  derivePatternIntakeFromWorkflow,
  buildPatternSavedChatText,
  type WorkflowProposalContext,
} from './patternMemoryProposalRuntime';
import { validatePatternMemoryIntake } from './patternMemoryRuntime';

// ── derivePatternIntakeFromWorkflow ──────────────────────────────────────────

describe('derivePatternIntakeFromWorkflow', () => {
  const baseCtx: WorkflowProposalContext = {
    mission: 'Füge einen Dark-Mode-Toggle zur Einstellungsseite hinzu.',
    repoOwner: 'OuroborosCollective',
    repoName: 'Sovereign-Studio-ato',
    prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/42',
    now: 1_700_000_000_000,
  };

  it('produces a valid PatternMemoryIntake accepted by the runtime validator', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    const report = validatePatternMemoryIntake(intake);
    expect(report.valid).toBe(true);
    expect(report.errors).toHaveLength(0);
  });

  it('sets ownerScope to local-user', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    expect(intake.ownerScope).toBe('local-user');
  });

  it('sets verified and localExecutable to false', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    expect(intake.verified).toBe(false);
    expect(intake.localExecutable).toBe(false);
  });

  it('includes draft-pr and workflow-complete tags', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    expect(intake.tags).toContain('draft-pr');
    expect(intake.tags).toContain('workflow-complete');
  });

  it('includes repo name as a tag', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    expect(intake.tags).toContain('sovereign-studio-ato');
  });

  it('stores the PR URL as objectRef', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    expect(intake.objectRef).toBe(baseCtx.prUrl);
  });

  it('title is truncated to 80 chars', () => {
    const longMission = 'A'.repeat(200);
    const intake = derivePatternIntakeFromWorkflow({ ...baseCtx, mission: longMission });
    expect(intake.title.length).toBeLessThanOrEqual(80);
  });

  it('summary contains the PR URL, repo, and mission', () => {
    const intake = derivePatternIntakeFromWorkflow(baseCtx);
    expect(intake.summary).toContain(baseCtx.prUrl);
    expect(intake.summary).toContain(baseCtx.repoOwner);
    expect(intake.summary).toContain(baseCtx.repoName);
    expect(intake.summary).toContain(baseCtx.mission);
  });

  it('summary is within the 800 char limit', () => {
    const intake = derivePatternIntakeFromWorkflow({
      ...baseCtx,
      mission: 'M'.repeat(1000),
    });
    expect(intake.summary.length).toBeLessThanOrEqual(800);
  });

  it('sourceTraceId is stable across identical calls', () => {
    const a = derivePatternIntakeFromWorkflow(baseCtx);
    const b = derivePatternIntakeFromWorkflow(baseCtx);
    expect(a.sourceTraceId).toBe(b.sourceTraceId);
  });

  it('sourceTraceId differs when mission differs', () => {
    const a = derivePatternIntakeFromWorkflow(baseCtx);
    const b = derivePatternIntakeFromWorkflow({ ...baseCtx, mission: 'other task' });
    expect(a.sourceTraceId).not.toBe(b.sourceTraceId);
  });

  it('redacts GitHub tokens from mission text', () => {
    const intake = derivePatternIntakeFromWorkflow({
      ...baseCtx,
      mission: 'Use token ghp_abc123xyz456 for access',
    });
    expect(intake.title).not.toContain('ghp_');
    expect(intake.summary).not.toContain('ghp_');
  });

  it('handles empty repoOwner and repoName gracefully', () => {
    const intake = derivePatternIntakeFromWorkflow({
      ...baseCtx,
      repoOwner: '',
      repoName: '',
    });
    const report = validatePatternMemoryIntake(intake);
    expect(report.valid).toBe(true);
  });

  it('handles empty mission by falling back to repo label', () => {
    const intake = derivePatternIntakeFromWorkflow({ ...baseCtx, mission: '' });
    expect(intake.title.length).toBeGreaterThan(0);
    const report = validatePatternMemoryIntake(intake);
    expect(report.valid).toBe(true);
  });
});

// ── buildPatternSavedChatText ────────────────────────────────────────────────

describe('buildPatternSavedChatText', () => {
  it('includes the pattern title', () => {
    const text = buildPatternSavedChatText(
      'My Pattern',
      'https://github.com/owner/repo/pull/1',
      'owner',
      'repo',
    );
    expect(text).toContain('My Pattern');
  });

  it('includes the PR URL', () => {
    const prUrl = 'https://github.com/owner/repo/pull/99';
    const text = buildPatternSavedChatText('T', prUrl, 'owner', 'repo');
    expect(text).toContain(prUrl);
  });

  it('includes the repo label', () => {
    const text = buildPatternSavedChatText('T', 'https://x.com/pr/1', 'Acme', 'my-repo');
    expect(text).toContain('Acme/my-repo');
  });

  it('still renders when repoOwner and repoName are empty', () => {
    const text = buildPatternSavedChatText('T', 'https://x.com', '', '');
    expect(text.length).toBeGreaterThan(0);
  });

  it('contains the German success marker', () => {
    const text = buildPatternSavedChatText('T', 'https://x.com', 'o', 'r');
    expect(text).toContain('✅');
  });
});
