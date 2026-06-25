import { describe, expect, it } from 'vitest';
import {
  CUTE_KAOMOJI_FRAMES,
  CUTE_THINKING_FRAMES,
  formatCuteThinkingLabel,
  getCuteKaomojiFrame,
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

  it('always includes a kaomoji in formatted labels', () => {
    const label = formatCuteThinkingLabel({ index: 5, active: true, status: 'running' });

    expect(CUTE_KAOMOJI_FRAMES.some((kaomoji) => label.includes(kaomoji))).toBe(true);
  });

  it('picks deterministic kaomoji frames from the index', () => {
    expect(getCuteKaomojiFrame(0)).toBe(getCuteKaomojiFrame(0));
    expect(CUTE_KAOMOJI_FRAMES).toContain(getCuteKaomojiFrame(12));
  });

  it('formats active labels with soft thinking dots and status', () => {
    const label = formatCuteThinkingLabel({ index: 1, active: true, status: 'running' });

    expect(label).toContain('...');
    expect(label).toContain('running');
  });
});
