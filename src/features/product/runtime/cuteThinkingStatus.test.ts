import { describe, expect, it } from 'vitest';
import {
  CUTE_THINKING_FRAMES,
  formatCuteThinkingLabel,
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

  it('formats active labels with soft thinking dots and status', () => {
    const label = formatCuteThinkingLabel({ index: 1, active: true, status: 'running' });

    expect(label).toContain('...');
    expect(label).toContain('running');
  });
});
