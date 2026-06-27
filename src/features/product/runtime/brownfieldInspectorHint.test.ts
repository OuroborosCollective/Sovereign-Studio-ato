import { describe, expect, it } from 'vitest';
import { buildBrownfieldInspectorHint } from './brownfieldInspectorHint';

describe('brownfieldInspectorHint', () => {
  it('stays hidden when no repo tree is loaded', () => {
    const hint = buildBrownfieldInspectorHint({
      repoName: 'Empty',
      branch: 'main',
      files: [],
    });

    expect(hint.visible).toBe(false);
    expect(hint.lamp).toBe('red');
    expect(hint.message).toContain('Noch kein Repo-Baum');
    expect(hint.targetTab).toBe('health');
  });

  it('creates a red health hint for critical Brownfield signals', () => {
    const hint = buildBrownfieldInspectorHint({
      repoName: 'Critical Repo',
      branch: 'main',
      files: ['package.json', 'src/App.tsx', 'src/main.tsx'],
    });

    expect(hint.visible).toBe(true);
    expect(hint.lamp).toBe('red');
    expect(hint.targetTab).toBe('health');
    expect(hint.message).toContain('kritische');
    expect(hint.report.findings.some((finding) => finding.severity === 'critical')).toBe(true);
  });

  it('creates a yellow findings hint for warning-only repo debt', () => {
    const hint = buildBrownfieldInspectorHint({
      repoName: 'Warn Repo',
      branch: 'main',
      files: [
        'package.json',
        'pnpm-lock.yaml',
        'src/legacy/OldFeature.tsx',
        'src/App.tsx',
        'src/App.test.tsx',
      ],
    });

    expect(hint.visible).toBe(true);
    expect(hint.lamp).toBe('yellow');
    expect(hint.targetTab).toBe('findings');
    expect(hint.message).toContain('prüfenswerte');
    expect(hint.detail).toContain('Hotspots');
  });

  it('creates a green quiet hint for stable file trees', () => {
    const hint = buildBrownfieldInspectorHint({
      repoName: 'Stable Repo',
      branch: 'main',
      files: [
        { path: 'package.json' },
        { path: 'pnpm-lock.yaml' },
        { path: 'src/App.tsx' },
        { path: 'src/App.test.tsx' },
        { path: 'src/main.tsx' },
        { path: 'src/main.test.tsx' },
      ],
    });

    expect(hint.visible).toBe(true);
    expect(hint.lamp).toBe('green');
    expect(hint.targetTab).toBe('findings');
    expect(hint.message).toContain('wirkt stabil');
  });
});
