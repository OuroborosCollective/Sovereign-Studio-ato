import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('live entry guard', () => {
  it('renders the current container application from the app entry', () => {
    const mainPath = path.join(process.cwd(), 'src', 'main.tsx');
    const main = readFileSync(mainPath, 'utf8');
    const staleShellName = ['Product', 'Magic', 'App'].join('');

    expect(main).toContain("import App from './App'");
    expect(main).toContain('<App />');
    expect(main).not.toContain(staleShellName);
  });
});
