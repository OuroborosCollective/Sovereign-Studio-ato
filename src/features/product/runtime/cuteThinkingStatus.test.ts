import { describe, expect, it } from 'vitest';
import {
  CUTE_KAOMOJI_FRAMES,
  CUTE_THINKING_FRAMES,
  CUTE_WORKSTATE_DOT_FRAMES,
  formatCuteThinkingLabel,
  formatCuteWorkStateLabel,
  getCuteKaomojiFrame,
  getCuteWorkStateDotFrame,
  getCuteThinkingFrame,
  normalizeThinkingFrameIndex,
} from './cuteThinkingStatus';

describe('cuteThinkingStatus', () => {
  it('wraps frame indexes without inventing progress', () => {
    expect(normalizeThinkingFrameIndex(0)).toBe(0);
    expect(normalizeThinkingFrameIndex(CUTE_THINKING_FRAMES.length)).toBe(0);
    expect(normalizeThinkingFrameIndex(-1)).toBe(0);
  });

  it('returns an idle frame when the runtime is not active', () => {
    const frame = getCuteThinkingFrame(3, false);

    expect(frame.text).toContain('bereit');
  });

  it('rotates through chick working phrases while runtime is active', () => {
    expect(CUTE_THINKING_FRAMES.some((frame) => frame.text.includes('Küken piepst'))).toBe(true);
    expect(CUTE_THINKING_FRAMES.some((frame) => frame.text.includes('Küken sucht Körner'))).toBe(true);
    expect(CUTE_THINKING_FRAMES.some((frame) => frame.text.includes('Küken schreibt'))).toBe(true);
  });

  it('uses status-aware chick phrases for working and code states', () => {
    const running = getCuteThinkingFrame(1, true, 'Agent arbeitet');
    const coding = getCuteThinkingFrame(2, true, 'Ich schreibe Code');

    expect(running.text).toMatch(/Küken|Piep/);
    expect(coding.text).toMatch(/Küken|Piep|Code/);
  });

  it('uses a soft done phrase when work completed', () => {
    const done = getCuteThinkingFrame(4, true, 'completed');

    expect(done.text).toBe('Küken hat fertig gepiepst');
  });

  it('always includes a kaomoji in formatted labels', () => {
    const label = formatCuteThinkingLabel({ index: 5, active: true, status: 'running' });

    expect(CUTE_KAOMOJI_FRAMES.some((kaomoji) => label.includes(kaomoji))).toBe(true);
  });

  it('picks deterministic random-looking kaomoji frames from index and salt', () => {
    expect(getCuteKaomojiFrame(0, 11)).toBe(getCuteKaomojiFrame(0, 11));
    expect(CUTE_KAOMOJI_FRAMES).toContain(getCuteKaomojiFrame(12, 99));
  });

  it('formats active labels with soft thinking dots and status', () => {
    const label = formatCuteThinkingLabel({ index: 1, active: true, status: 'running' });

    expect(label).toContain('...');
    expect(label).toContain('running');
    expect(label).toMatch(/Küken|Piep/);
  });

  it('cycles visible workstate dots without numeric progress', () => {
    expect(CUTE_WORKSTATE_DOT_FRAMES).toEqual(['...', '..', '.']);
    expect(getCuteWorkStateDotFrame(0)).toBe('...');
    expect(getCuteWorkStateDotFrame(1)).toBe('..');
    expect(getCuteWorkStateDotFrame(2)).toBe('.');
    expect(getCuteWorkStateDotFrame(3)).toBe('...');
  });

  it('formats active workstate labels with kaomoji and changing dots', () => {
    const label = formatCuteWorkStateLabel({ index: 2, active: true, status: 'OpenHands läuft' });

    expect(label).toContain('.');
    expect(label).toContain('OpenHands läuft');
    expect(CUTE_KAOMOJI_FRAMES.some((kaomoji) => label.includes(kaomoji))).toBe(true);
    expect(label).not.toMatch(/\d+%/);
  });

  it('formats idle workstate labels as a real idle state', () => {
    const label = formatCuteWorkStateLabel({ index: 4, active: false });

    expect(label).toContain('idle');
    expect(CUTE_KAOMOJI_FRAMES.some((kaomoji) => label.includes(kaomoji))).toBe(true);
    expect(label).not.toContain('completed');
  });

});
