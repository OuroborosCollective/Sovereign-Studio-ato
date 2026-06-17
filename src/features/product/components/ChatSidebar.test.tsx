import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { ChatSidebar } from './ChatSidebar';
import { ChatMessage, Suggestion } from '../types';

const BASE_TIME = 1_700_000_000_000;

describe('ChatSidebar', () => {
  const mockChatMessages: ChatMessage[] = [
    { id: '1', role: 'assistant', content: 'Willkommen!', timestamp: BASE_TIME },
    { id: '2', role: 'user', content: 'Hallo', timestamp: BASE_TIME + 1000 },
  ];

  const mockSuggestions: Suggestion[] = [
    {
      id: 's1',
      type: 'feature',
      title: 'Integration: WebSocket',
      description: 'Empfohlene Integration',
      priority: 'high',
    },
    {
      id: 's2',
      type: 'error',
      title: 'Security Risk',
      description: 'Fehlende Auth',
      priority: 'high',
    },
  ];

  const defaultProps = {
    chatMessages: mockChatMessages,
    suggestions: mockSuggestions,
    isAnalyzing: false,
    onSendMessage: vi.fn(),
    onAcceptSuggestion: vi.fn(),
    onDownloadPackage: vi.fn(),
    onClearChat: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders chat messages correctly', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByText('Willkommen!')).toBeDefined();
      expect(screen.getByText('Hallo')).toBeDefined();
    });

    it('renders suggestions section when suggestions exist', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByText(/Vorschläge/i)).toBeDefined();
      expect(screen.getByRole('button', { name: /Accept suggestion: Integration: WebSocket/i })).toBeDefined();
    });

    it('renders input field for user messages', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByRole('textbox', { name: /Chat Nachricht/i })).toBeDefined();
    });

    it('shows analyzing indicator when isAnalyzing is true', () => {
      render(<ChatSidebar {...defaultProps} isAnalyzing />);

      expect(screen.getByLabelText(/Analyse läuft/i)).toBeDefined();
    });

    it('renders empty state when no messages', () => {
      render(<ChatSidebar {...defaultProps} chatMessages={[]} />);

      expect(screen.getByRole('textbox', { name: /Chat Nachricht/i })).toBeDefined();
      expect(screen.getByRole('button', { name: /Nachricht senden/i })).toBeDisabled();
    });
  });

  describe('User Interaction', () => {
    it('calls onSendMessage when form is submitted', () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat Nachricht/i });
      const submitButton = screen.getByRole('button', { name: /Nachricht senden/i });

      fireEvent.change(input, { target: { value: '  Test   message  ' } });
      fireEvent.click(submitButton);

      expect(defaultProps.onSendMessage).toHaveBeenCalledWith('Test message');
    });

    it('clears input after submission', () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat Nachricht/i }) as HTMLInputElement;
      const submitButton = screen.getByRole('button', { name: /Nachricht senden/i });

      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.click(submitButton);

      expect(input.value).toBe('');
    });

    it('calls onAcceptSuggestion when suggestion is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);

      fireEvent.click(screen.getByRole('button', { name: /Accept suggestion: Integration: WebSocket/i }));
      expect(defaultProps.onAcceptSuggestion).toHaveBeenCalledWith('s1');
    });

    it('does not call onAcceptSuggestion for accepted suggestions', () => {
      render(
        <ChatSidebar
          {...defaultProps}
          suggestions={[{ ...mockSuggestions[0], accepted: true }]}
        />,
      );

      const acceptedButton = screen.getByRole('button', { name: /Accepted suggestion: Integration: WebSocket/i });
      expect(acceptedButton).toBeDisabled();
      fireEvent.click(acceptedButton);
      expect(defaultProps.onAcceptSuggestion).not.toHaveBeenCalled();
    });

    it('calls onClearChat when clear button is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);

      fireEvent.click(screen.getByRole('button', { name: /Chat leeren/i }));
      expect(defaultProps.onClearChat).toHaveBeenCalledOnce();
    });

    it('calls onDownloadPackage when download button is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);

      fireEvent.click(screen.getByRole('button', { name: /Verlauf sichern/i }));
      expect(defaultProps.onDownloadPackage).toHaveBeenCalledOnce();
    });

    it('disables submit button when input is empty', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByRole('button', { name: /Nachricht senden/i })).toBeDisabled();
    });

    it('enables submit button when input has content', async () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat Nachricht/i });
      const submitButton = screen.getByRole('button', { name: /Nachricht senden/i });

      fireEvent.change(input, { target: { value: 'Test' } });

      await waitFor(() => {
        expect(submitButton).not.toBeDisabled();
      });
    });
  });

  describe('Styling', () => {
    it('applies correct style to user messages', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByText('Hallo')).toBeDefined();
    });

    it('applies correct style to assistant messages', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByText('Willkommen!')).toBeDefined();
    });

    it('shows accepted state for accepted suggestions', () => {
      render(
        <ChatSidebar
          {...defaultProps}
          suggestions={[{ ...mockSuggestions[0], accepted: true }]}
        />,
      );

      expect(screen.getByText('✓ Integration: WebSocket')).toBeDefined();
      expect(screen.getByRole('button', { name: /Accepted suggestion: Integration: WebSocket/i })).toHaveAttribute('aria-pressed', 'true');
    });

    it('shows priority badges for high priority suggestions', () => {
      render(<ChatSidebar {...defaultProps} />);

      const badges = screen.queryAllByText('WICHTIG');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  describe('Runtime normalization', () => {
    it('normalizes empty ids, blank messages and unsafe suggestion labels before rendering', () => {
      render(
        <ChatSidebar
          {...defaultProps}
          chatMessages={[
            { id: '', role: 'assistant', content: '  normalized   message  ', timestamp: BASE_TIME },
            { id: 'blank', role: 'assistant', content: '   ', timestamp: BASE_TIME + 1 },
          ]}
          suggestions={[{ id: '', type: 'feature', title: '', description: '  fallback desc  ', priority: 'low' }]}
        />,
      );

      expect(screen.getByText('normalized message')).toBeDefined();
      expect(screen.queryByText('blank')).toBeNull();
      expect(screen.getByRole('button', { name: /Accept suggestion: Untitled suggestion/i })).toBeDefined();
      expect(screen.getByTestId('chat-sidebar')).toHaveAttribute('data-summary', '1 message(s), 1 suggestion(s), 0 accepted.');
    });
  });

  describe('Error Handling', () => {
    it('handles empty suggestions array gracefully', () => {
      render(<ChatSidebar {...defaultProps} suggestions={[]} />);

      expect(screen.queryByText(/Vorschläge/i)).toBeNull();
    });

    it('handles very long messages', () => {
      const longMessage: ChatMessage = {
        id: 'long',
        role: 'assistant',
        content: 'A'.repeat(1000),
        timestamp: BASE_TIME + 2000,
      };

      render(<ChatSidebar {...defaultProps} chatMessages={[longMessage]} />);

      expect(screen.getByText('A'.repeat(1000))).toBeDefined();
    });
  });
});
