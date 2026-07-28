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

  it('should not allow links with embedded null bytes', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](jav\x00ascript:alert(1))" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });

  it('should not allow links with leading/embedded whitespace', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me]( java\tscript:alert(2))" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });

  it('should allow whitelisted safe protocol https', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](https://example.com)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("https://example.com");
  });

  it('should allow whitelisted safe protocol http', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](http://example.com)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("http://example.com");
  });

  it('should allow whitelisted safe protocol mailto', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](mailto:support@example.com)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("mailto:support@example.com");
  });

  it('should allow relative paths', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](/relative/path)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("/relative/path");
  });

  it('should allow local anchors', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](#anchor)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("#anchor");
  });

  it('should block non-whitelisted protocols like file:', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](file:///etc/passwd)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });

  it('should block non-whitelisted protocols like ftp:', () => {
    const { getByRole } = render(<ChatMarkdown content="[Click me](ftp://example.com)" />);
    const link = getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe("about:blank");
  });
});
