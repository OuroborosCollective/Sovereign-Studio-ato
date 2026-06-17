import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('live entry guard', () => {
  it('renders the current container application from the app entry', () => {
    const main = readFileSync(new URL('./main.tsx', import.meta.url), 'utf8');
    const staleShellName = ['Product', 'Magic', 'App'].join('');

    expect(main).toContain("import App from './App'");
    expect(main).toContain('<App />');
    expect(main).not.toContain(staleShellName);
  });
});
