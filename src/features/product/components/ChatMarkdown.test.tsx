/**
 * ChatMarkdown tests
 * Tests for markdown rendering (bold, code, links, code blocks)
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown', () => {
  it('renders plain text', () => {
    const { container } = render(<ChatMarkdown content="Hello world" />);
    expect(container.textContent).toContain('Hello world');
  });

  it('renders bold text', () => {
    const { container } = render(<ChatMarkdown content="This is **bold** text" />);
    const strong = container.querySelector('strong');
    expect(strong).toBeTruthy();
    expect(strong?.textContent).toBe('bold');
  });

  it('renders multiple bold sections', () => {
    const { container } = render(<ChatMarkdown content="**first** and **second**" />);
    const strongs = container.querySelectorAll('strong');
    expect(strongs).toHaveLength(2);
    expect(strongs[0].textContent).toBe('first');
    expect(strongs[1].textContent).toBe('second');
  });

  it('renders inline code', () => {
    const { container } = render(<ChatMarkdown content="Use `console.log()` for debugging" />);
    const code = container.querySelector('code');
    expect(code).toBeTruthy();
    expect(code?.textContent).toBe('console.log()');
  });

  it('renders code block', () => {
    const { container } = render(<ChatMarkdown content="```typescript\nconst x = 1;\n```" />);
    // Code block renders with language label
    expect(container.textContent).toContain('typescript');
  });

  it('renders code block with language', () => {
    const { container } = render(<ChatMarkdown content="```javascript\nalert('hi');\n```" />);
    expect(container.textContent).toContain('javascript');
  });

  it('renders links', () => {
    const { container } = render(<ChatMarkdown content="Check [this link](https://example.com)" />);
    const link = container.querySelector('a');
    expect(link).toBeTruthy();
    expect(link?.href).toBe('https://example.com/');
    expect(link?.textContent).toBe('this link');
  });

  it('handles mixed content', () => {
    const { container } = render(<ChatMarkdown content="Use **bold** and `code` together" />);
    expect(container.querySelector('strong')?.textContent).toBe('bold');
    expect(container.querySelector('code')?.textContent).toBe('code');
  });

  it('handles empty content', () => {
    const { container } = render(<ChatMarkdown content="" />);
    expect(container.textContent).toBe('');
  });

  it('handles non-string content gracefully', () => {
    const { container } = render(<ChatMarkdown content={null as unknown as string} />);
    expect(container.textContent).toBe('null');
  });

  it('renders multiline with code block and text', () => {
    const { container } = render(<ChatMarkdown content="Before\n\n```js\ncode\n```\n\nAfter" />);
    // Code block renders with language label
    expect(container.textContent).toContain('js');
    expect(container.textContent).toContain('Before');
    expect(container.textContent).toContain('After');
  });

  it('preserves plain text line breaks as visible breaks', () => {
    const { container } = render(<ChatMarkdown content={"A.\nB.\nC."} />);
    expect(container.querySelectorAll('br')).toHaveLength(2);
    expect(container.textContent).toBe('A.B.C.');
  });

  it('preserves text formatting in same line', () => {
    const { container } = render(<ChatMarkdown content="**bold** normal `code` normal" />);
    const text = container.textContent || '';
    expect(text).toContain('bold');
    expect(text).toContain('normal');
    expect(text).toContain('code');
  });

  it('handles copy button click in code blocks', async () => {
    // Mock clipboard
    const originalClipboard = navigator.clipboard;
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const { getByRole, findByText } = render(<ChatMarkdown content={"```typescript\nconst x = 1;\n```"} />);

    const copyButton = getByRole('button', { name: 'Copy code' });
    expect(copyButton).toBeTruthy();
    expect(copyButton.textContent).toBe('Copy');

    await act(async () => {
      fireEvent.click(copyButton);
    });

    expect(writeTextMock).toHaveBeenCalledWith('const x = 1;');
    expect(copyButton.textContent).toBe('✓ Copied');

    // Restore clipboard
    Object.assign(navigator, {
      clipboard: originalClipboard,
    });
  });
});
