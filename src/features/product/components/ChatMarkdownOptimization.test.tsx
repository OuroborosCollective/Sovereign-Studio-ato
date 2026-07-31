/**
 * ChatMarkdownOptimization.test.tsx
 * Tests to verify performance caching and hit-rates on inlineLineCache and tokenizeContent 1-slot cache.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import {
  ChatMarkdown,
  inlineLineCache,
  getInlineSegmentsForLine,
  lastTokenizeInput,
  lastTokenizeResult,
  clearTokenizeCache
} from './ChatMarkdown';

describe('ChatMarkdown Performance Optimization', () => {
  beforeEach(() => {
    clearTokenizeCache();
  });

  it('populates and uses the inlineLineCache correctly', () => {
    const line = 'This is a **special** optimization line with `code`';

    // First call: cache miss
    const segments1 = getInlineSegmentsForLine(line);
    expect(inlineLineCache.has(line)).toBe(true);
    expect(segments1).toBeDefined();

    // Verify cache has the computed segments
    const cachedSegments = inlineLineCache.get(line);
    expect(cachedSegments).toBe(segments1);

    // Second call: cache hit (returns referentially identical segments array)
    const segments2 = getInlineSegmentsForLine(line);
    expect(segments2).toBe(segments1);
  });

  it('populates and utilizes the 1-slot full-text tokenizeContent cache', () => {
    const text = 'Line 1\nLine 2 with **bold** text\nLine 3 with `code`';

    // Before rendering, caches are empty
    expect(lastTokenizeInput).toBeNull();
    expect(lastTokenizeResult).toHaveLength(0);

    // Render 1st time
    const { rerender } = render(<ChatMarkdown content={text} />);

    // Cache should now contain the text and results
    expect(lastTokenizeInput).toBe(text);
    const firstResult = lastTokenizeResult;
    expect(firstResult.length).toBeGreaterThan(0);

    // Render 2nd time with identical text
    rerender(<ChatMarkdown content={text} />);
    expect(lastTokenizeInput).toBe(text);
    // Since 1-slot cache was used, the result must be referentially identical
    expect(lastTokenizeResult).toBe(firstResult);
  });

  it('bounds the inlineLineCache size to prevent memory leaks', () => {
    // Fill the cache up to its threshold (1000 items)
    for (let i = 0; i < 1000; i++) {
      getInlineSegmentsForLine(`dummy-line-identifier-${i}`);
    }
    expect(inlineLineCache.size).toBe(1000);

    // Add 1001st line which triggers cache clearing
    getInlineSegmentsForLine('triggering-limit-line');
    // It clears first and then inserts the new item, so size becomes 1
    expect(inlineLineCache.size).toBe(1);
    expect(inlineLineCache.has('triggering-limit-line')).toBe(true);
  });
});
