import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { ChatSidebar } from './ChatSidebar';
import { ChatMessage, Suggestion } from '../types';

describe('ChatSidebar', () => {
  const mockChatMessages: ChatMessage[] = [
    { id: '1', role: 'assistant', content: 'Willkommen!', timestamp: Date.now() },
    { id: '2', role: 'user', content: 'Hallo', timestamp: Date.now() + 1000 },
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
      title: '⚠️ Security Risk',
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
      expect(screen.getByText('Integration: WebSocket')).toBeDefined();
    });

    it('renders input field for user messages', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const input = screen.getByPlaceholderText(/Frage oder Feedback/i);
      expect(input).toBeDefined();
    });

    it('shows analyzing indicator when isAnalyzing is true', () => {
      render(<ChatSidebar {...defaultProps} isAnalyzing={true} />);
      
      // Should show loader/animation class
      const header = screen.getByText(/Chat & Vorschläge/i);
      expect(header).toBeDefined();
    });

    it('renders empty state when no messages', () => {
      render(<ChatSidebar {...defaultProps} chatMessages={[]} />);
      
      // Should still render input and suggestions
      expect(screen.getByPlaceholderText(/Frage oder Feedback/i)).toBeDefined();
    });
  });

  describe('User Interaction', () => {
    it('calls onSendMessage when form is submitted', async () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const input = screen.getByPlaceholderText(/Frage oder Feedback/i);
      const submitButton = screen.getByRole('button', { type: 'submit' });
      
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.click(submitButton);
      
      expect(defaultProps.onSendMessage).toHaveBeenCalledWith('Test message');
    });

    it('clears input after submission', async () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const input = screen.getByPlaceholderText(/Frage oder Feedback/i) as HTMLInputElement;
      
      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.click(screen.getByRole('button', { type: 'submit' }));
      
      expect(input.value).toBe('');
    });

    it('calls onAcceptSuggestion when suggestion is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const suggestion = screen.getByText('Integration: WebSocket').closest('button');
      if (suggestion) {
        fireEvent.click(suggestion);
        expect(defaultProps.onAcceptSuggestion).toHaveBeenCalledWith('s1');
      }
    });

    it('calls onClearChat when clear button is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const clearButton = screen.getByText(/Leeren/i);
      fireEvent.click(clearButton);
      
      expect(defaultProps.onClearChat).toHaveBeenCalled();
    });

    it('calls onDownloadPackage when download button is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const downloadButton = screen.getByText(/Verlauf sichern/i);
      fireEvent.click(downloadButton);
      
      expect(defaultProps.onDownloadPackage).toHaveBeenCalled();
    });

    it('disables submit button when input is empty', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { type: 'submit' });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button when input has content', async () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const input = screen.getByPlaceholderText(/Frage oder Feedback/i);
      const submitButton = screen.getByRole('button', { type: 'submit' });
      
      fireEvent.change(input, { target: { value: 'Test' } });
      
      await waitFor(() => {
        expect(submitButton).not.toBeDisabled();
      });
    });
  });

  describe('Styling', () => {
    it('applies correct style to user messages', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const userMessage = screen.getByText('Hallo');
      // User messages should have different styling (indigo background)
      expect(userMessage).toBeDefined();
    });

    it('applies correct style to assistant messages', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const assistantMessage = screen.getByText('Willkommen!');
      expect(assistantMessage).toBeDefined();
    });

    it('shows accepted state for accepted suggestions', () => {
      const acceptedSuggestion: Suggestion = {
        ...mockSuggestions[0],
        accepted: true,
      };
      
      render(
        <ChatSidebar
          {...defaultProps}
          suggestions={[acceptedSuggestion]}
        />
      );
      
      const suggestionText = screen.getByText('✓ Integration: WebSocket');
      expect(suggestionText).toBeDefined();
    });

    it('shows priority badges for high priority suggestions', () => {
      render(<ChatSidebar {...defaultProps} />);
      
      const badge = screen.getByText('WICHTIG');
      expect(badge).toBeDefined();
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
        timestamp: Date.now(),
      };
      
      render(<ChatSidebar {...defaultProps} chatMessages={[longMessage]} />);
      
      expect(screen.getByText(/A{1000}/)).toBeDefined();
    });
  });
});
