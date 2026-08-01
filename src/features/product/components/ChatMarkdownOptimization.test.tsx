// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { ChatMarkdown, inlineLineCache, clearChatMarkdownCaches } from './ChatMarkdown';

describe('ChatMarkdown Optimization & Caching', () => {
  beforeEach(() => {
    clearChatMarkdownCaches();
  });

  it('correctly populates inlineLineCache during tokenization', () => {
    expect(inlineLineCache.size).toBe(0);

    const testLine1 = 'This is a line with **bold** text';
    const testLine2 = 'Another line with `inline code`';
    const content = `${testLine1}\n${testLine2}`;

    render(<ChatMarkdown content={content} />);

    // Each line should be cached separately
    expect(inlineLineCache.has(testLine1)).toBe(true);
    expect(inlineLineCache.has(testLine2)).toBe(true);
    expect(inlineLineCache.size).toBe(2);

    // Grab cached segments
    const cached1 = inlineLineCache.get(testLine1);
    expect(cached1).toBeDefined();
    expect(cached1?.some((s) => s.type === 'bold' && s.content === 'bold')).toBe(true);

    const cached2 = inlineLineCache.get(testLine2);
    expect(cached2).toBeDefined();
    expect(cached2?.some((s) => s.type === 'code' && s.content === 'inline code')).toBe(true);
  });

  it('leverages cached line segments on subsequent renders', () => {
    const testLine = 'Repeatable **bold** line';

    // First render to populate the cache
    render(<ChatMarkdown content={testLine} />);
    expect(inlineLineCache.has(testLine)).toBe(true);

    const initialCachedArray = inlineLineCache.get(testLine);
    expect(initialCachedArray).toBeDefined();

    // Modify the cached value to see if it is used (proving cache hit)
    const modifiedSegments = [{ type: 'text' as const, content: 'Intercepted Cache Content' }];
    inlineLineCache.set(testLine, modifiedSegments);

    // Render again with the same line (clearing whole-text cache to force line-level lookups)
    clearChatMarkdownCaches();
    inlineLineCache.set(testLine, modifiedSegments);

    const { container } = render(<ChatMarkdown content={testLine} />);
    expect(container.textContent).toBe('Intercepted Cache Content');
  });

  it('bounds the line cache size to at most 1000 items and evicts', () => {
    // Fill the cache to its limit
    for (let i = 0; i < 999; i++) {
      inlineLineCache.set(`line-${i}`, [{ type: 'text', content: `val-${i}` }]);
    }
    expect(inlineLineCache.size).toBe(999);

    // One more should be fine
    inlineLineCache.set('line-999', [{ type: 'text', content: 'val-999' }]);
    expect(inlineLineCache.size).toBe(1000);

    // Rendering or retrieving a new line will exceed 1000 and trigger eviction/reset
    render(<ChatMarkdown content="A new line that will trigger eviction" />);

    // Size should reset and only contain the newly parsed line
    expect(inlineLineCache.size).toBe(1);
    expect(inlineLineCache.has('A new line that will trigger eviction')).toBe(true);
  });

  it('leverages the 1-slot whole-text tokenizer cache for duplicate consecutive text evaluations', () => {
    const testText = 'Hello world\nThis is a long streamed response';

    // We can observe cache hits by rendering multiple times with the same input.
    // To verify that the whole-text evaluation isn't executing line-by-line parsing again,
    // let's clear the line cache but NOT the 1-slot tokenizer cache.
    render(<ChatMarkdown content={testText} />);

    // Clear the line-level cache, leaving only the 1-slot tokenizer cache active
    inlineLineCache.clear();
    expect(inlineLineCache.size).toBe(0);

    // Second render of the same consecutive text
    const { container } = render(<ChatMarkdown content={testText} />);
    expect(container.textContent).toContain('Hello world');
    expect(container.textContent).toContain('This is a long streamed response');

    // The line cache remained empty because tokenizeContent bypassed parsing by using the 1-slot cache!
    expect(inlineLineCache.size).toBe(0);
  });
});
