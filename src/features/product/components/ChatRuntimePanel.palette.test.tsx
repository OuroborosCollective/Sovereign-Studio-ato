import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ChatRuntimePanel } from './ChatRuntimePanel';

// Mock the hooks and contexts
vi.mock('../hooks/useRuntimeModelHealth', () => ({
  useRuntimeModelHealth: () => ({
    isChecking: false,
    lastCheck: null,
    refresh: vi.fn(),
    fallbackResult: { proceed: true, strategy: 'primary' },
  }),
}));

vi.mock('../contexts/LlmAdapterContext', () => ({
  useAllLlmAdapters: () => [],
}));

describe('ChatRuntimePanel Palette Improvements', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should have localized ARIA labels for accessibility', () => {
    render(<ChatRuntimePanel />);

    expect(screen.getByLabelText('Status aktualisieren')).toBeDefined();
    expect(screen.getByLabelText('Eingabe, Auftrag oder Frage')).toBeDefined();
    expect(screen.getByLabelText('Nachricht senden')).toBeDefined();
  });

  it('should show clear button only when input has text', () => {
    render(<ChatRuntimePanel />);

    // Initially no clear button
    expect(screen.queryByLabelText('Eingabe loeschen')).toBeNull();

    const input = screen.getByLabelText('Eingabe, Auftrag oder Frage');
    fireEvent.change(input, { target: { value: 'Hello' } });

    // Clear button should appear
    const clearButton = screen.getByLabelText('Eingabe loeschen');
    expect(clearButton).toBeDefined();

    // Clicking clear should empty input and refocus
    fireEvent.click(clearButton);
    expect((input as HTMLInputElement).value).toBe('');
    expect(document.activeElement).toBe(input);
  });
});
