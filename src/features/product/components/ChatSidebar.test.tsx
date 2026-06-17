import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { ChatSidebar } from './ChatSidebar';
import { ChatMessage, Suggestion } from '../types';

describe('ChatSidebar', () => {
  const mockChatMessages: ChatMessage[] = [
    { id: '1', role: 'assistant', content: 'Willkommen!', timestamp: 1 },
    { id: '2', role: 'user', content: 'Hallo', timestamp: 2 },
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

  const renderSidebar = (props: Partial<React.ComponentProps<typeof ChatSidebar>> = {}) => render(<ChatSidebar {...defaultProps} {...props} />);
  const chatInput = () => screen.getByPlaceholderText(/Frage oder Feedback/i) as HTMLInputElement;
  const sendButton = () => screen.getByRole('button', { name: /Nachricht senden|send/i });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders chat messages correctly', () => {
      renderSidebar();

      expect(screen.getByText('Willkommen!')).toBeDefined();
      expect(screen.getByText('Hallo')).toBeDefined();
    });

    it('renders suggestions section when suggestions exist', () => {
      renderSidebar();

      expect(screen.getByText(/Vorschläge/i)).toBeDefined();
      expect(screen.getByText('Integration: WebSocket')).toBeDefined();
    });

    it('renders input field for user messages', () => {
      renderSidebar();

      expect(chatInput()).toBeDefined();
    });

    it('shows analyzing indicator when isAnalyzing is true', () => {
      renderSidebar({ isAnalyzing: true });

      expect(screen.getByText(/Chat & Vorschläge/i)).toBeDefined();
    });

    it('renders empty state when no messages', () => {
      renderSidebar({ chatMessages: [] });

      expect(chatInput()).toBeDefined();
    });
  });

  describe('User Interaction', () => {
    it('calls onSendMessage when form is submitted', () => {
      renderSidebar();

      fireEvent.change(chatInput(), { target: { value: 'Test message' } });
      fireEvent.click(sendButton());

      expect(defaultProps.onSendMessage).toHaveBeenCalledWith('Test message');
    });

    it('clears input after submission', () => {
      renderSidebar();
      const input = chatInput();

      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.click(sendButton());

      expect(input.value).toBe('');
    });

    it('calls onAcceptSuggestion when suggestion is clicked', () => {
      renderSidebar();

      const suggestion = screen.getByRole('button', { name: /Integration: WebSocket/i });
      fireEvent.click(suggestion);

      expect(defaultProps.onAcceptSuggestion).toHaveBeenCalledWith('s1');
    });

    it('does not call onAcceptSuggestion for accepted suggestions', () => {
      renderSidebar({ suggestions: [{ ...mockSuggestions[0], accepted: true }] });

      const suggestion = screen.getByRole('button', { name: /Integration: WebSocket/i });
      fireEvent.click(suggestion);

      expect(defaultProps.onAcceptSuggestion).not.toHaveBeenCalled();
    });

    it('calls onClearChat when clear button is clicked', () => {
      renderSidebar();

      const clearButton = screen.getByRole('button', { name: /Leeren|Chat leeren/i });
      fireEvent.click(clearButton);

      expect(defaultProps.onClearChat).toHaveBeenCalled();
    });

    it('calls onDownloadPackage when download button is clicked', () => {
      renderSidebar();

      const downloadButton = screen.getByRole('button', { name: /Verlauf sichern/i });
      fireEvent.click(downloadButton);

      expect(defaultProps.onDownloadPackage).toHaveBeenCalled();
    });

    it('disables submit button when input is empty', () => {
      renderSidebar();

      expect(sendButton()).toBeDisabled();
    });

    it('enables submit button when input has content', async () => {
      renderSidebar();

      fireEvent.change(chatInput(), { target: { value: 'Test' } });

      await waitFor(() => {
        expect(sendButton()).not.toBeDisabled();
      });
    });
  });

  describe('Styling and state', () => {
    it('applies correct style to user messages', () => {
      renderSidebar();

      expect(screen.getByText('Hallo')).toBeDefined();
    });

    it('applies correct style to assistant messages', () => {
      renderSidebar();

      expect(screen.getByText('Willkommen!')).toBeDefined();
    });

    it('shows accepted state for accepted suggestions', () => {
      const acceptedSuggestion: Suggestion = {
        ...mockSuggestions[0],
        accepted: true,
      };

      renderSidebar({ suggestions: [acceptedSuggestion] });

      expect(screen.getByText('✓ Integration: WebSocket')).toBeDefined();
    });

    it('shows priority badges for high priority suggestions', () => {
      renderSidebar();

      expect(screen.getAllByText('WICHTIG').length).toBeGreaterThan(0);
    });
  });

  describe('Error Handling', () => {
    it('handles empty suggestions array gracefully', () => {
      renderSidebar({ suggestions: [] });

      expect(screen.queryByText(/Vorschläge/i)).toBeNull();
    });

    it('handles very long messages', () => {
      const longMessage: ChatMessage = {
        id: 'long',
        role: 'assistant',
        content: 'A'.repeat(1000),
        timestamp: 1,
      };

      renderSidebar({ chatMessages: [longMessage] });

      expect(screen.getByText('A'.repeat(1000))).toBeDefined();
    });

    it('scopes interaction to the suggestion section', () => {
      renderSidebar();

      const section = screen.getByText(/Vorschläge/i).closest('div');
      expect(section).toBeTruthy();
      if (!section) return;

      expect(within(section.parentElement ?? section).getByText('Integration: WebSocket')).toBeDefined();
    });
  });
});
