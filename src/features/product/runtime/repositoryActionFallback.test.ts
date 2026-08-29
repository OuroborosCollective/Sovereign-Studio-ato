import { describe, expect, it } from 'vitest';
import { deriveRepositoryActionFallback } from './repositoryActionFallback';

describe('repository action degraded fallback', () => {
  it('recovers a documentation mutation after an invalid online action contract', () => {
    expect(deriveRepositoryActionFallback(
      'Bitte passe die repository doku an mit dem heutigen Datum!',
    )).toEqual({
      intent: 'direct_patch',
      actionTitle: 'Bitte passe die repository doku an mit dem heutigen Datum!',
    });
  });

  it('does not turn ordinary conversation into a repository mutation', () => {
    expect(deriveRepositoryActionFallback('Wie geht es dir heute?')).toBeNull();
  });

  it('bounds the user-owned title and never consumes provider prose', () => {
    const result = deriveRepositoryActionFallback('Aktualisiere die Dokumentation ' + 'x'.repeat(400));
    expect(result?.actionTitle.length).toBe(180);
  });
});
