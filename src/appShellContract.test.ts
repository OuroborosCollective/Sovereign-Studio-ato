import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('current Sovereign app shell contract', () => {
  it('renders the container App instead of the removed ProductMagic shell', () => {
    const main = read('src/main.tsx');

    expect(main).toContain("import App from './App'");
    expect(main).toContain('<App />');
    expect(main).not.toContain('ProductMagicApp');
  });

  it('keeps the core container imports reachable from App.tsx', () => {
    const app = read('src/App.tsx');

    expect(app).toContain('RemoteMemoryContainer');
    expect(app).toContain('BuilderContainer');
    expect(app).toContain('WorkflowContainer');
    expect(app).toContain('RepoSnapshotContainer');
    expect(app).toContain('TelemetryContainer');
    expect(app).toContain('PatternMemoryContainer');
  });

  it('starts in the repo workflow instead of hiding the app behind the monitor', () => {
    const app = read('src/App.tsx');

    expect(app).toContain("useState<SovereignTab>('repo')");
    expect(app).toContain("{ id: 'repo', label: 'Repo' }");
    expect(app).toContain("{ id: 'builder', label: 'Builder' }");
    expect(app).toContain("{ id: 'remote', label: 'Remote Memory' }");
    expect(app).toContain("{ id: 'memory', label: 'Pattern Memory' }");
  });

  it('keeps the Android shell mobile-only and landscape safe', () => {
    const css = read('src/index.css');
    const main = read('src/main.tsx');

    expect(css).toContain('Android phones, foldables and tablets only');
    expect(css).toContain('@media (orientation: landscape)');
    expect(css).toContain('grid-template-columns: 1fr');
    expect(css).not.toContain('desktop-like');
    expect(main).toContain('clamp(5.35rem, 12vw, 8rem)');
  });
});
