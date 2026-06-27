import { describe, expect, it } from 'vitest';
import { decidePalRoute } from './palRouter';

describe('palRouter', () => {
  it('routes explanation-only requests to fast tier without repo requirement', () => {
    const decision = decidePalRoute({
      mission: 'Erklär mir kurz, was diese App macht',
      repoReady: false,
      repoFileCount: 0,
    });

    expect(decision.blocked).toBe(false);
    expect(decision.intent).toBe('answer');
    expect(decision.tier).toBe('fast');
    expect(decision.signal).toBe('green');
    expect(decision.recommendedAction).toBe('Direkt beantworten.');
  });

  it('blocks repo work until a real repo snapshot exists', () => {
    const decision = decidePalRoute({
      mission: 'Baue mir ein Feature in das Repo',
      repoReady: false,
      repoFileCount: 0,
    });

    expect(decision.blocked).toBe(true);
    expect(decision.signal).toBe('yellow');
    expect(decision.tier).toBe('fast');
    expect(decision.reason).toContain('Repo-Snapshot');
  });

  it('routes repair work on larger repos to power tier', () => {
    const decision = decidePalRoute({
      mission: 'Fix die roten Workflow Fehler und Typecheck Gates',
      repoReady: true,
      repoFileCount: 650,
      automationMode: 'auto-review',
    });

    expect(decision.blocked).toBe(false);
    expect(decision.intent).toBe('repair');
    expect(decision.tier).toBe('power');
    expect(decision.signal).toBe('yellow');
    expect(decision.facts).toContain('files=650');
  });

  it('routes large repo scans above fast tier', () => {
    const decision = decidePalRoute({
      mission: 'Analysiere die Architektur und Brownfield Hotspots',
      repoReady: true,
      repoFileCount: 1500,
      automationMode: 'manual',
    });

    expect(decision.blocked).toBe(false);
    expect(decision.intent).toBe('repo-scan');
    expect(decision.tier).toBe('power');
    expect(decision.reason).toContain('1500');
  });

  it('routes normal code changes to balanced tier', () => {
    const decision = decidePalRoute({
      mission: 'Implementiere den neuen Runtime Hook',
      repoReady: true,
      repoFileCount: 120,
    });

    expect(decision.blocked).toBe(false);
    expect(decision.intent).toBe('code-change');
    expect(decision.tier).toBe('balanced');
    expect(decision.signal).toBe('green');
  });

  it('routes draft PR work to power tier with review reminder', () => {
    const decision = decidePalRoute({
      mission: 'Draft PR erstellen',
      repoReady: true,
      repoFileCount: 75,
    });

    expect(decision.blocked).toBe(false);
    expect(decision.intent).toBe('draft-pr');
    expect(decision.tier).toBe('power');
    expect(decision.recommendedAction).toContain('Generated-File-Review');
  });

  it('hard-blocks routing when runtime blockers exist', () => {
    const decision = decidePalRoute({
      mission: 'Fix die App',
      repoReady: true,
      repoFileCount: 400,
      blockers: ['GitHub PAT fehlt'],
    });

    expect(decision.blocked).toBe(true);
    expect(decision.signal).toBe('red');
    expect(decision.tier).toBe('fast');
    expect(decision.recommendedAction).toBe('GitHub PAT fehlt');
    expect(decision.facts).toContain('blockers=1');
  });
});
