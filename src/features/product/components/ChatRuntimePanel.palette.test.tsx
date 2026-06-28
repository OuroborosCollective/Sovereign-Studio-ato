import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ChatRuntimePanel } from './ChatRuntimePanel';
import { LlmAdapterProvider } from '../contexts/LlmAdapterContext';

describe('ChatRuntimePanel Palette Enhancements', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderPanel = () => {
    return render(
      <LlmAdapterProvider>
        <ChatRuntimePanel />
      </LlmAdapterProvider>
    );
  };

  it('renders Send button with correct accessibility attributes', () => {
    renderPanel();
    const sendButton = screen.getByRole('button', { name: /Send message/i });
    expect(sendButton).toBeTruthy();
    expect(sendButton).toHaveAttribute('title', 'Send message');
  });

  it('renders Refresh button with correct accessibility attributes', () => {
    renderPanel();
    const refreshButton = screen.getByRole('button', { name: /Refresh health/i });
    expect(refreshButton).toBeTruthy();
    expect(refreshButton).toHaveAttribute('title', 'Refresh health');
  });

  it('shows Clear button when there is input', () => {
    renderPanel();
    const input = screen.getByLabelText('Chat message');

    // Initially no clear button
    expect(screen.queryByLabelText('Clear input')).toBeNull();

    // Type something
    fireEvent.change(input, { target: { value: 'Hello' } });

    // Clear button should appear
    const clearButton = screen.getByRole('button', { name: /Clear input/i });
    expect(clearButton).toBeTruthy();
    expect(clearButton).toHaveAttribute('title', 'Clear input');

    // Click clear button
    fireEvent.click(clearButton);

    // Input should be empty
    expect((input as HTMLInputElement).value).toBe('');

    // Clear button should disappear
    expect(screen.queryByLabelText('Clear input')).toBeNull();

    // Input should have focus
    expect(input).toHaveFocus();
  });
});
