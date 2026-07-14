import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown Palette Enhancements', () => {
  it('renders code blocks with accessibility attributes', () => {
    const content = '```typescript\nconst x = 1;\n```';
    render(<ChatMarkdown content={content} />);

    // Check for the language label title
    const languageLabel = screen.getByText('typescript');
    expect(languageLabel).toHaveAttribute('title', 'Language: typescript');

    // Check for the pre element accessibility attributes
    const preElement = screen.getByRole('region');
    expect(preElement).toHaveAttribute('aria-label', 'Code block (typescript)');
    expect(preElement).toHaveAttribute('tabIndex', '0');
  });

  it('renders copy button with accessibility attributes', () => {
    const content = '```text\nsome code\n```';
    render(<ChatMarkdown content={content} />);

    const copyButton = screen.getByRole('button', { name: /Copy code/i });
    expect(copyButton).toHaveAttribute('title', 'Copy code');
  });
});
