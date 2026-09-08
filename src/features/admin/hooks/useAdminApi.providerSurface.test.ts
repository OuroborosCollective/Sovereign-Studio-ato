import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('admin provider surface retirement', () => {
  it('does not expose an OmniRoute refresh action through the admin hook', () => {
    const source = readFileSync(new URL('./useAdminApi.ts', import.meta.url), 'utf8');

    expect(source).not.toContain('refreshOmniRoute');
    expect(source).not.toContain('OmniRouteRuntimeStatus');
  });
});
