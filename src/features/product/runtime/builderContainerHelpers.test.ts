import { describe, expect, it } from 'vitest';
import { buildOutcomeHints, safeHttpsUrl } from './builderContainerHelpers';

describe('safeHttpsUrl', () => {
  it('returns valid https URLs', () => {
    expect(safeHttpsUrl('https://github.com/owner/repo/pull/1')).toBe(
      'https://github.com/owner/repo/pull/1'
    );
  });

  it('rejects non-https protocols', () => {
    expect(safeHttpsUrl('http://github.com/owner/repo')).toBeUndefined();
    expect(safeHttpsUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeHttpsUrl('data:text/html,test')).toBeUndefined();
  });

  it('rejects malformed or unparseable URLs', () => {
    expect(safeHttpsUrl('https://')).toBeUndefined();
    expect(safeHttpsUrl('https:// invalid host')).toBeUndefined();
    expect(safeHttpsUrl('https://\njavascript:alert(1)')).toBeUndefined();
  });

  it('returns undefined for empty, null, or undefined inputs', () => {
    expect(safeHttpsUrl(undefined)).toBeUndefined();
    expect(safeHttpsUrl('')).toBeUndefined();
    expect(safeHttpsUrl('   ')).toBeUndefined();
  });
});

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
