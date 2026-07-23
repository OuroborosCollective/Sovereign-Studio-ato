import { describe, expect, it } from 'vitest';
import { buildImpactReport, findImporters } from './dependencyImpactRuntime';

const sources = [
  { path: 'src/a.ts', content: "import { login } from './auth';" },
  { path: 'src/b.ts', content: "const auth = require('./auth');" },
  { path: 'src/c.ts', content: "export const value = 1;" },
  { path: 'src/auth.ts', content: 'export const login = () => true;' },
];

describe('dependencyImpactRuntime', () => {
  it('finds deterministic importers from supplied source evidence', () => {
    expect(findImporters('src/auth.ts', sources)).toEqual(['src/a.ts', 'src/b.ts']);
  });

  it('marks a partial scan as incomplete instead of implying repo-wide truth', () => {
    const report = buildImpactReport(['src/auth.ts'], sources, { complete: false });
    expect(report.byTarget['src/auth.ts'].importerCount).toBe(2);
    expect(report.byTarget['src/auth.ts'].scannedFileCount).toBe(4);
    expect(report.byTarget['src/auth.ts'].complete).toBe(false);
  });
});
