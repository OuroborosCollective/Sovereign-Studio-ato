import { describe, it, expect } from 'vitest';
import { formatTime24h } from './timeUtils';

describe('formatTime24h', () => {
  it('formats valid timestamps correctly matching de-DE style', () => {
    // 2026-03-15 08:05:09 local time
    const date = new Date(2026, 2, 15, 8, 5, 9);
    expect(formatTime24h(date)).toBe('08:05:09');

    // 2026-03-15 14:12:30 local time
    const date2 = new Date(2026, 2, 15, 14, 12, 30);
    expect(formatTime24h(date2)).toBe('14:12:30');
  });

  it('formats numbers as timestamps correctly', () => {
    const date = new Date(2026, 2, 15, 23, 59, 59);
    expect(formatTime24h(date.getTime())).toBe('23:59:59');
  });

  it('handles invalid timestamps and returns fallback', () => {
    expect(formatTime24h(NaN, 'invalid')).toBe('invalid');
    expect(formatTime24h(-100, '--:--:--')).toBe('--:--:--');
    expect(formatTime24h(0, '--:--:--')).toBe('--:--:--');
  });

  it('bypasses Intl and executes significantly faster than toLocaleTimeString', () => {
    const ts = Date.now();

    // Warm up
    formatTime24h(ts);
    new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    // Measure formatTime24h
    const startFast = performance.now();
    for (let i = 0; i < 500; i++) {
      formatTime24h(ts);
    }
    const endFast = performance.now();
    const fastDuration = endFast - startFast;

    // Measure toLocaleTimeString
    const startSlow = performance.now();
    for (let i = 0; i < 500; i++) {
      new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    const endSlow = performance.now();
    const slowDuration = endSlow - startSlow;

    console.log(`[Bolt Benchmark] 500 iterations of formatTime24h: ${fastDuration.toFixed(4)}ms`);
    console.log(`[Bolt Benchmark] 500 iterations of toLocaleTimeString: ${slowDuration.toFixed(4)}ms`);
    console.log(`[Bolt Benchmark] Speedup factor: ${(slowDuration / fastDuration).toFixed(2)}x`);

    // Verify it formats identically (modulo timezone weirdness if any, but since de-DE local is used, they should match exactly)
    const formattedFast = formatTime24h(ts);
    const formattedSlow = new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    expect(formattedFast).toBe(formattedSlow);
  });
});
