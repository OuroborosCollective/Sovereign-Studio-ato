import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { UserApiKeys } from './userApiKeysContract';

function source(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8');
}

describe('User API key runtime contract', () => {
  it('keeps provider runtime modules independent from React component types', () => {
    const validationSource = source('src/features/product/runtime/apiKeyValidation.ts');
    const providerSource = source('src/features/product/runtime/providerRuntimeChecks.ts');

    expect(validationSource).not.toContain('../components/');
    expect(providerSource).not.toContain('../components/');
    expect(validationSource).toContain("from './userApiKeysContract'");
    expect(providerSource).toContain("from './userApiKeysContract'");
  });

  it('supports only the neutral provider-key shape', () => {
    const keys: UserApiKeys = {
      groq: 'gsk_example',
      gemini: 'AIza_example',
    };

    expect(Object.keys(keys).sort()).toEqual(['gemini', 'groq']);
  });
});
