import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AndroidMessageBubble } from './AndroidMessageBubble';

describe('AndroidMessageBubble', () => {
  it('opens actions on context menu and quotes text', () => {
    const onQuote = vi.fn();
    render(<AndroidMessageBubble role="assistant" text="hello" onQuote={onQuote} />);
    fireEvent.contextMenu(screen.getByTestId('android-message-bubble'));
    fireEvent.click(screen.getByText('Zitieren'));
    expect(onQuote).toHaveBeenCalledWith('hello');
  });

  it('renders user text', () => {
    render(<AndroidMessageBubble role="user" text="plain user" onQuote={() => {}} />);
    expect(screen.getByText('plain user')).toBeTruthy();
  });

  it('applies focus styles correctly', () => {
    render(<AndroidMessageBubble role="assistant" text="hello" onQuote={() => {}} />);

    // Test copy button focus
    const copyButton = screen.getByRole('button', { name: /Nachricht kopieren/i });
    expect(copyButton.style.outline).toBe('none');

    fireEvent.focus(copyButton);
    expect(copyButton.style.outline).toContain('solid');

    fireEvent.blur(copyButton);
    expect(copyButton.style.outline).toBe('none');

    // Open context menu to test menu buttons focus
    fireEvent.contextMenu(screen.getByTestId('android-message-bubble'));

    const quoteButton = screen.getByText('Zitieren');
    expect(quoteButton.style.outline).toBe('none');

    fireEvent.focus(quoteButton);
    expect(quoteButton.style.outline).toContain('solid');

    fireEvent.blur(quoteButton);
    expect(quoteButton.style.outline).toBe('none');

    // Test focus reset on click
    fireEvent.focus(quoteButton);
    expect(quoteButton.style.outline).toContain('solid');
    fireEvent.click(quoteButton);

    // Menu closes and quoteButton is unmounted, but we should verify behavior
    // Just executing to ensure no errors.
  });
});
