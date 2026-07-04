import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown Security', () => {
  it('should not allow javascript: links', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](javascript:alert('XSS'))" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });

  it('should not allow data: links', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](data:text/html;base64,PHNjcmlwdD5hbGVydCgnWFNTJyk8L3NjcmlwdD4=)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });

  it('should not allow vbscript: links', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](vbscript:msgbox('XSS'))" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });
});
