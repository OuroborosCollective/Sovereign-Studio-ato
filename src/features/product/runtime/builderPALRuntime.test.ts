import { describe, expect, it } from 'vitest';
import { palRoute, type PALDecision } from './builderPALRuntime';

describe('builderPALRuntime', () => {
  it('routes short simple messages with no context to fast tier', () => {
    const decision = palRoute('Hallo', 0, 0, []);
    expect(decision.tier).toBe('fast');
    expect(decision.score).toBe(0);
    expect(decision.costFactor).toBe(1);
    expect(decision.modelId).toBe('sovereign-fast');
  });

  it('routes medium messages with files and history to smart tier', () => {
    const message = 'Kannst du diese Funktion in `src/utils.ts` refactorn und mir erklären, wie sie funktioniert?';
    const decision = palRoute(message, 15, 3, []);
    expect(decision.score).toBeGreaterThan(33);
    expect(decision.tier).toBe('smart');
    expect(decision.costFactor).toBe(10);
    expect(decision.modelId).toBe('sovereign-balanced');
  });

  it('scores code blocks correctly using fast triple-backtick index scanning', () => {
    const message = 'Hier ist der Code:\n```ts\nconst x = 1;\n```\nUnd noch ein Block:\n```ts\nconst y = 2;\n```\n' + 'A'.repeat(300);
    const decision = palRoute(message, 12, 5, []);
    // Message len >= 300 (+15)
    // 4 triple backticks = 2 code blocks ((4 / 2) * 5 = +10)
    // fileCount > 0 (+10)
    // histDepth > 10 (+5)
    // total score = 40 -> smart tier
    expect(decision.score).toBe(40);
    expect(decision.tier).toBe('smart');
  });

  it('routes high complexity queries to power tier', () => {
    const longMessage = 'Analyze system architecture\n' + '```\ncode block 1\n```\n' + '```\ncode block 2\n```\n' + '```\ncode block 3\n```\n' + 'x'.repeat(400);
    const decision = palRoute(longMessage, 20, 10, []);
    // score > 66 -> power
    expect(decision.tier).toBe('power');
    expect(decision.costFactor).toBe(30);
  });

  it('downgrades power tier to smart tier when power tier limit is reached', () => {
    const longMessage = 'Analyze system architecture\n' + '```\ncode block 1\n```\n' + '```\ncode block 2\n```\n' + '```\ncode block 3\n```\n' + 'x'.repeat(400);
    const powerPriors: PALDecision[] = Array.from({ length: 10 }, () => ({
      tier: 'power',
      modelId: 'sovereign-balanced',
      modelLabel: 'Sovereign Balanced',
      score: 80,
      costFactor: 30,
    }));
    const decision = palRoute(longMessage, 20, 10, powerPriors);
    expect(decision.tier).toBe('smart');
  });
});
