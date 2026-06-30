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
});
