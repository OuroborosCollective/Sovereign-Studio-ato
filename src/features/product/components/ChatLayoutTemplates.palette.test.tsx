import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ChatLayoutTemplates } from './ChatLayoutTemplates';

describe('ChatLayoutTemplates Palette Accessibility Enhancements', () => {
  const baseProps = {
    chatMessages: [],
    suggestions: [],
    isAnalyzing: false,
    onSendMessage: vi.fn(),
    onAcceptSuggestion: vi.fn(),
    onDownloadPackage: vi.fn(),
    onClearChat: vi.fn(),
  };

  describe('Terminal Layout', () => {
    it('Send button has correct aria-label and title', () => {
      render(<ChatLayoutTemplates {...baseProps} layout="terminal" />);
      const sendButton = screen.getByRole('button', { name: /Send/i });
      expect(sendButton).toHaveAttribute('aria-label', 'Send');
      expect(sendButton).toHaveAttribute('title', 'Send');
    });
  });

  describe('Floating Layout', () => {
    it('Send button has correct aria-label and title', () => {
      render(<ChatLayoutTemplates {...baseProps} layout="floating" />);
      const sendButton = screen.getByRole('button', { name: /Send/i });
      expect(sendButton).toHaveAttribute('aria-label', 'Send');
      expect(sendButton).toHaveAttribute('title', 'Send');
    });

    it('Clear input button has correct aria-label and title when input is present', () => {
      render(<ChatLayoutTemplates {...baseProps} layout="floating" />);
      const input = screen.getByPlaceholderText(/Ask or describe/i);

      fireEvent.change(input, { target: { value: 'Hello' } });

      const clearButton = screen.getByRole('button', { name: /Clear input/i });
      expect(clearButton).toHaveAttribute('aria-label', 'Clear input');
      expect(clearButton).toHaveAttribute('title', 'Clear input');
    });
  });

  describe('Split-View Layout', () => {
    it('Send button has correct aria-label and title', () => {
      render(<ChatLayoutTemplates {...baseProps} layout="split-view" />);
      const sendButton = screen.getByRole('button', { name: /Send/i });
      expect(sendButton).toHaveAttribute('aria-label', 'Send');
      expect(sendButton).toHaveAttribute('title', 'Send');
    });
  });

  describe('Layout Selector', () => {
    it('Layout buttons have correct aria-label and title', () => {
      render(<ChatLayoutTemplates {...baseProps} />);

      const terminalButton = screen.getByRole('button', { name: /Terminal/i });
      expect(terminalButton).toHaveAttribute('aria-label', 'Terminal');
      expect(terminalButton).toHaveAttribute('title', 'Minimal, command-oriented');

      const floatingButton = screen.getByRole('button', { name: /Floating/i });
      expect(floatingButton).toHaveAttribute('aria-label', 'Floating');
      expect(floatingButton).toHaveAttribute('title', 'Classic chat with bubbles');

      const splitViewButton = screen.getByRole('button', { name: /Split-View/i });
      expect(splitViewButton).toHaveAttribute('aria-label', 'Split-View');
      expect(splitViewButton).toHaveAttribute('title', 'Chat + Code side-by-side');
    });
  });
});
