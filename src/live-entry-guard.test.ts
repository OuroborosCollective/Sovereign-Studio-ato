import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('live entry guard', () => {
  it('renders the current composition wrapper from the app entry', () => {
    const mainPath = path.join(process.cwd(), 'src', 'main.tsx');
    const wrapperPath = path.join(process.cwd(), 'src', 'SovereignAppWrapper.tsx');
    const main = readFileSync(mainPath, 'utf8');
    const wrapper = readFileSync(wrapperPath, 'utf8');
    const staleShellName = ['Product', 'Magic', 'App'].join('');

    expect(main).toContain("import App from './SovereignAppWrapper'");
    expect(main).toContain('<App />');
    expect(wrapper).toContain("import App from './App'");
    expect(wrapper).toContain('<App />');
    expect(main).not.toContain(staleShellName);
    expect(wrapper).not.toContain(staleShellName);
  });
});
