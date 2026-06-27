import { describe, expect, it } from 'vitest';
import { mergeQuietInspectorSignals, type QuietInspectorSignal } from './quietInspectorHintPolicy';

function signal(overrides: Partial<QuietInspectorSignal>): QuietInspectorSignal {
  return {
    id: 'default',
    source: 'Test',
    lamp: 'green',
    message: 'Alles ok',
    targetTab: 'findings',
    visible: true,
    updatedAt: 1,
    ...overrides,
  };
}

describe('quietInspectorHintPolicy', () => {
  it('returns a calm empty result when there are no visible signals', () => {
    const result = mergeQuietInspectorSignals([
      signal({ id: 'hidden', visible: false, lamp: 'red' }),
    ]);

    expect(result.hasVisibleSignals).toBe(false);
    expect(result.topLamp).toBe('green');
    expect(result.summary).toBe('Keine neuen Inspector-Hinweise.');
    expect(result.signals).toEqual([]);
  });

  it('prioritizes blockers before warnings and ok signals', () => {
    const result = mergeQuietInspectorSignals([
      signal({ id: 'ok', lamp: 'green', message: 'Repo verbunden', targetTab: 'repo' }),
      signal({ id: 'warn', lamp: 'yellow', message: 'Remote Memory hat Hinweise', targetTab: 'remote' }),
      signal({ id: 'blocker', lamp: 'red', message: 'Health Blocker gefunden', targetTab: 'health' }),
    ]);

    expect(result.hasVisibleSignals).toBe(true);
    expect(result.topLamp).toBe('red');
    expect(result.signals.map((item) => item.id)).toEqual(['blocker', 'warn', 'ok']);
    expect(result.summary).toContain('1 Blocker');
    expect(result.summary).toContain('1 Hinweise');
    expect(result.summary).toContain('1 OK');
  });

  it('limits visible signals to keep the chat quiet', () => {
    const result = mergeQuietInspectorSignals(
      Array.from({ length: 8 }, (_, index) => signal({ id: `s-${index}`, lamp: 'yellow', updatedAt: index })),
    );

    expect(result.signals).toHaveLength(5);
    expect(result.signals[0].id).toBe('s-7');
  });

  it('sanitizes noisy messages without fabricating content', () => {
    const result = mergeQuietInspectorSignals([
      signal({ id: ' noisy ', source: ' Telemetry ', message: '  Viele    Leerzeichen   im Hinweis  ', targetTab: 'telemetry' }),
    ]);

    expect(result.signals[0].id).toBe('noisy');
    expect(result.signals[0].source).toBe('Telemetry');
    expect(result.signals[0].message).toBe('Viele Leerzeichen im Hinweis');
  });
});
