import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8');
}

describe('main app entry', () => {
  it('renders the current Sovereign container app, not the legacy ProductMagic shell', () => {
    const main = readSource('./main.tsx');

    expect(main).toContain("import App from './App'");
    expect(main).toContain('<App />');
    expect(main).not.toContain("import ProductMagicApp from './ProductMagicApp'");
    expect(main).not.toContain('<ProductMagicApp />');
  });

  it('keeps visible container app navigation and runtime surfaces available', () => {
    const app = readSource('./App.tsx');

    for (const label of [
      'Repo',
      'Builder',
      'Files',
      'Diff',
      'Workflow',
      'Repair',
      'Remote Memory',
      'Pattern Memory',
      'Telemetry',
      'Live Monitor',
      'Readiness',
      'Integrity',
      'Findings',
      'Health',
      'Runtime',
      'Coverage',
    ]) {
      expect(app).toContain(`label: '${label}'`);
    }
  });

  it('wires the runtime auto-view router into the live app shell', () => {
    const app = readSource('./App.tsx');

    expect(app).toContain('decideSovereignAutoView');
    expect(app).toContain("view:auto-switch");
    expect(app).toContain('setActiveTab(decision.tab)');
    expect(app).toContain('workflowStatus: workflowReport?.status');
  });

  it('keeps the release shell styling contract in the Android web build', () => {
    const css = readSource('./index.css');

    expect(css).toContain('--surface-1');
    expect(css).toContain('--accent-2');
    expect(css).toContain('Release shell');
    expect(css).toContain('Container runtime');
    expect(css).toContain('Signed Android artifacts');
  });
});
