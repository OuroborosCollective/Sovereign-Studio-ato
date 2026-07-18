import { describe, expect, it } from 'vitest';
import {
  createAssistantResponsePacingState,
  sliceAssistantResponseWords,
} from './assistantResponsePacingRuntime';

describe('response pacing runtime', () => {
  it('keeps short messages immediate', () => {
    const state = createAssistantResponsePacingState('short text', 1);

    expect(state.shouldPace).toBe(false);
    expect(state.visibleText).toBe('short text');
    expect(state.complete).toBe(true);
  });

  describe('sliceAssistantResponseWords with caching optimization', () => {
    it('returns empty string when visibleWords <= 0', () => {
      expect(sliceAssistantResponseWords('hello world', 0)).toBe('');
      expect(sliceAssistantResponseWords('hello world', -5)).toBe('');
    });

    it('slices correctly at word boundaries including trailing spaces', () => {
      const text = 'hello world how are you';
      expect(sliceAssistantResponseWords(text, 1)).toBe('hello ');
      expect(sliceAssistantResponseWords(text, 2)).toBe('hello world ');
      expect(sliceAssistantResponseWords(text, 3)).toBe('hello world how ');
    });

    it('returns complete text when visibleWords >= total words', () => {
      const text = 'hello world';
      expect(sliceAssistantResponseWords(text, 2)).toBe('hello world');
      expect(sliceAssistantResponseWords(text, 3)).toBe('hello world');
      expect(sliceAssistantResponseWords(text, 100)).toBe('hello world');
    });

    it('leverages 1-slot caching correctly and is accurate on consecutive and non-consecutive runs', () => {
      const text1 = 'the quick brown fox';
      const text2 = 'jumps over the lazy dog';

      // First run on text1 (populates cache)
      expect(sliceAssistantResponseWords(text1, 2)).toBe('the quick ');

      // Consecutive run on text1 (uses cache)
      expect(sliceAssistantResponseWords(text1, 3)).toBe('the quick brown ');

      // Run on different text2 (updates cache)
      expect(sliceAssistantResponseWords(text2, 2)).toBe('jumps over ');

      // Run on text1 again (updates cache again)
      expect(sliceAssistantResponseWords(text1, 1)).toBe('the ');
    });
  });
});
