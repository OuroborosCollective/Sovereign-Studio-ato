import { describe, expect, it } from 'vitest';
import { buildOutcomeHints } from './builderContainerHelpers';

describe('buildOutcomeHints', () => {
  it('does not render completed Sovereign Agent with no files and no draft PR as done', () => {
    const hints = buildOutcomeHints({
      status: 'completed',
      changedFiles: [],
      events: [],
    });

    expect(hints).toHaveLength(1);
    expect(hints[0]?.kind).toBe('stopper');
    expect(hints[0]?.text).toContain('keine Dateiänderung');
    expect(hints[0]?.text).toContain('kein Draft PR');
  });

  it('uses Draft PR evidence when a completed job includes a safe Draft PR URL', () => {
    const hints = buildOutcomeHints({
      status: 'completed',
      changedFiles: [],
      draftPrUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1',
      events: [],
    });

    expect(hints.some((hint) => hint.kind === 'draft-pr')).toBe(true);
    expect(hints.some((hint) => hint.kind === 'done')).toBe(false);
  });
});
