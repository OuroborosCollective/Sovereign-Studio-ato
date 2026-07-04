import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown Security', () => {
  it('should not allow javascript: links', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](javascript:alert('XSS'))" />);
    const link = getByRole('link') as HTMLAnchorElement;
    // We want to ensure the href is sanitized
    expect(link.getAttribute('href')).toBe("about:blank");
  });
});
