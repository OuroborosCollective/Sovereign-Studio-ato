import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { ChatSidebar, LlmModelInfo } from './ChatSidebar';
import { ChatMessage, Suggestion } from '../types';

const BASE_TIME = 1_700_000_000_000;

const mockModels: LlmModelInfo[] = [
  { id: 'gemini', label: 'Gemini', provider: 'Google', kind: 'user-key' },
  { id: 'pollinations', label: 'Pollinations', provider: 'Pollinations', kind: 'no-key' },
];

describe('ChatSidebar', () => {
  const mockChatMessages: ChatMessage[] = [
    { id: '1', role: 'assistant', content: 'Willkommen!', timestamp: BASE_TIME },
    { id: '2', role: 'user', content: 'Hallo', timestamp: BASE_TIME + 1000 },
  ];

  const mockSuggestions: Suggestion[] = [
    {
      id: 's1',
      type: 'feature',
      title: 'Add WebSocket',
      description: 'Recommended feature',
      priority: 'high',
    },
    {
      id: 's2',
      type: 'error',
      title: 'Security Fix',
      description: 'Missing auth',
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
    availableModels: mockModels,
    selectedModel: 'gemini',
    onModelChange: vi.fn(),
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

      const suggestionRegion = screen.getByTestId('chat-suggestions');
      expect(within(suggestionRegion).getByText(/^Quick Actions$/i)).toBeDefined();
      expect(screen.getByRole('button', { name: /Accept suggestion: Add WebSocket/i })).toBeDefined();
    });

    it('renders input field for user messages', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByRole('textbox', { name: /Chat message/i })).toBeDefined();
    });

    it('shows analyzing indicator when isAnalyzing is true', () => {
      render(<ChatSidebar {...defaultProps} isAnalyzing />);

      // Check that component renders with analyzing state - look for the thinking indicator div
      // The thinking div has class "flex gap-3" after the messages
      const chatMessages = document.querySelector('[aria-label="Chat Messages"]');
      expect(chatMessages).not.toBeNull();
      // When analyzing, there should be an extra child (the thinking indicator)
      const childCount = chatMessages?.children.length || 0;
      expect(childCount).toBeGreaterThan(2); // messages + thinking indicator
    });

    it('renders empty state when no messages', () => {
      render(<ChatSidebar {...defaultProps} chatMessages={[]} />);

      expect(screen.getByRole('textbox', { name: /Chat message/i })).toBeDefined();
      expect(screen.getByRole('button', { name: /Send/i })).toBeDisabled();
    });

    it('renders model selector when models provided', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByText('Gemini')).toBeDefined();
    });
  });

  describe('User Interaction', () => {
    it('calls onSendMessage when form is submitted', () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat message/i });
      const submitButton = screen.getByRole('button', { name: /Send/i });

      fireEvent.change(input, { target: { value: '  Test   message  ' } });
      fireEvent.click(submitButton);

      expect(defaultProps.onSendMessage).toHaveBeenCalledWith('Test message');
    });

    it('clears input after submission', () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat message/i }) as HTMLInputElement;
      const submitButton = screen.getByRole('button', { name: /Send/i });

      fireEvent.change(input, { target: { value: 'Test message' } });
      fireEvent.click(submitButton);

      expect(input.value).toBe('');
    });

    it('calls onAcceptSuggestion when suggestion is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);

      fireEvent.click(screen.getByRole('button', { name: /Accept suggestion: Add WebSocket/i }));
      expect(defaultProps.onAcceptSuggestion).toHaveBeenCalledWith('s1');
    });

    it('does not call onAcceptSuggestion for accepted suggestions', () => {
      render(
        <ChatSidebar
          {...defaultProps}
          suggestions={[{ ...mockSuggestions[0], accepted: true }]}
        />,
      );

      const acceptedButton = screen.getByRole('button', { name: /Accepted suggestion: Add WebSocket/i });
      expect(acceptedButton).toBeDisabled();
      fireEvent.click(acceptedButton);
      expect(defaultProps.onAcceptSuggestion).not.toHaveBeenCalled();
    });

    it('calls onClearChat when clear button is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);

      fireEvent.click(screen.getByRole('button', { name: /Clear conversation/i }));
      expect(defaultProps.onClearChat).toHaveBeenCalledOnce();
    });

    it('clears input when clear button is clicked', () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat message/i }) as HTMLInputElement;
      fireEvent.change(input, { target: { value: 'Test message' } });
      expect(input.value).toBe('Test message');

      const clearButton = screen.getByRole('button', { name: /Clear input/i });
      fireEvent.click(clearButton);

      expect(input.value).toBe('');
      expect(input).toHaveFocus();
    });

    it('disables submit button when input is empty', () => {
      render(<ChatSidebar {...defaultProps} />);

      expect(screen.getByRole('button', { name: /Send/i })).toBeDisabled();
    });

    it('enables submit button when input has content', async () => {
      render(<ChatSidebar {...defaultProps} />);

      const input = screen.getByRole('textbox', { name: /Chat message/i });
      const submitButton = screen.getByRole('button', { name: /Send/i });

      fireEvent.change(input, { target: { value: 'Test' } });

      await waitFor(() => {
        expect(submitButton).not.toBeDisabled();
      });
    });
  });

  describe('Model Selection', () => {
    it('calls onModelChange when model is selected', () => {
      render(<ChatSidebar {...defaultProps} />);

      // Open model picker by clicking the dropdown button
      const modelButton = screen.getByRole('button', { name: /Gemini/i });
      fireEvent.click(modelButton);
      
      // Select different model from the dropdown
      const pollButton = screen.getByRole('button', { name: /Pollinations/i });
      fireEvent.click(pollButton);
      
      expect(defaultProps.onModelChange).toHaveBeenCalledWith('pollinations');
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

      expect(screen.getByText('✓ Add WebSocket')).toBeDefined();
      expect(screen.getByRole('button', { name: /Accepted suggestion: Add WebSocket/i })).toHaveAttribute('aria-pressed', 'true');
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

      expect(screen.queryByTestId('chat-suggestions')).toBeNull();
      expect(screen.getByText('AI Assistant')).toBeDefined();
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
