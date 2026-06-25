import { describe, expect, it } from 'vitest';

import { deriveSovereignChatResultCards } from './sovereignChatWorkbenchResults';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

function snapshot(input: Partial<OpenHandsJobSnapshot>): OpenHandsJobSnapshot {
  return {
    status: 'idle',
    changedFiles: [],
    events: [],
    ...input,
  };
}

describe('sovereignChatWorkbenchResults', () => {
  it('returns no cards while OpenHands is idle', () => {
    expect(deriveSovereignChatResultCards(snapshot({ status: 'idle' }))).toEqual([]);
  });

  it('shows the real OpenHands runtime id without inventing progress', () => {
    const cards = deriveSovereignChatResultCards(snapshot({
      status: 'running',
      openHandsId: 'conv_real_123',
    }));

    expect(cards).toEqual([
      expect.objectContaining({
        kind: 'runtime-id',
        message: expect.stringContaining('conv_real_123'),
      }),
    ]);
  });

  it('summarizes changed files as a calm result card', () => {
    const cards = deriveSovereignChatResultCards(snapshot({
      status: 'running',
      changedFiles: ['src/App.tsx', 'src/features/product/runtime/x.ts', 'README.md'],
    }), { maxChangedFiles: 2 });

    const fileCard = cards.find((card) => card.kind === 'changed-files');

    expect(fileCard?.items).toEqual(['src/App.tsx', 'src/features/product/runtime/x.ts']);
    expect(fileCard?.message).toContain('1 weitere');
  });

  it('shows safe draft PR links only for https urls', () => {
    const safeCards = deriveSovereignChatResultCards(snapshot({
      status: 'completed',
      draftPrUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1',
    }));
    const unsafeCards = deriveSovereignChatResultCards(snapshot({
      status: 'completed',
      draftPrUrl: 'javascript:alert(1)',
    }));

    expect(safeCards.some((card) => card.kind === 'draft-pr')).toBe(true);
    expect(unsafeCards.some((card) => card.kind === 'draft-pr')).toBe(false);
  });

  it('shows blockers and failures as stopper cards', () => {
    const cards = deriveSovereignChatResultCards(snapshot({
      status: 'blocked',
      lastError: 'OpenHands API is not reachable',
    }));

    expect(cards).toEqual([
      expect.objectContaining({
        kind: 'stopper',
        message: 'OpenHands API is not reachable',
      }),
    ]);
  });

  it('shows a done card only when completed without files or draft pr', () => {
    const cards = deriveSovereignChatResultCards(snapshot({ status: 'completed' }));

    expect(cards).toEqual([
      expect.objectContaining({
        kind: 'completed',
        title: 'Küken hat fertig gepiepst',
      }),
    ]);
  });
});
