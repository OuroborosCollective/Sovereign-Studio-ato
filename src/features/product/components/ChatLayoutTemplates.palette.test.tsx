import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ChatLayoutTemplates } from './ChatLayoutTemplates';

describe('ChatLayoutTemplates Palette Accessibility', () => {
  beforeAll(() => {
    // Mock scrollIntoView for jsdom
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  const baseProps = {
    chatMessages: [],
    suggestions: [],
    isAnalyzing: false,
    onSendMessage: vi.fn(),
    onAcceptSuggestion: vi.fn(),
    onDownloadPackage: vi.fn(),
    onClearChat: vi.fn(),
    availableModels: [{ id: 'test-model', label: 'Test Model', provider: 'test', kind: 'test' }],
    selectedModel: 'test-model',
  };

  it('Layout selector buttons have aria-label and title', () => {
    render(<ChatLayoutTemplates {...baseProps} />);
    const terminalButton = screen.getByRole('button', { name: /Terminal: Minimal, befehlsorientiert/i });
    expect(terminalButton).toHaveAttribute('aria-label', 'Terminal: Minimal, befehlsorientiert');
    expect(terminalButton).toHaveAttribute('title', 'Minimal, befehlsorientiert');

    const floatingButton = screen.getByRole('button', { name: /Floating: Klassischer Chat mit Blasen/i });
    expect(floatingButton).toHaveAttribute('aria-label', 'Floating: Klassischer Chat mit Blasen');
    expect(floatingButton).toHaveAttribute('title', 'Klassischer Chat mit Blasen');
  });

  it('FloatingChatLayout Send button has aria-label and title', () => {
    render(<ChatLayoutTemplates {...baseProps} layout="floating" />);
    const sendButton = screen.getByRole('button', { name: /Senden/i });
    expect(sendButton).toHaveAttribute('aria-label', 'Senden');
    expect(sendButton).toHaveAttribute('title', 'Senden');
  });

  it('FloatingChatLayout Model Picker has aria attributes', () => {
    render(<ChatLayoutTemplates {...baseProps} layout="floating" />);
    const modelPicker = screen.getByRole('button', { name: /Modell auswählen/i });
    expect(modelPicker).toHaveAttribute('aria-label', 'Modell auswählen');
    expect(modelPicker).toHaveAttribute('title', 'Modell auswählen');
    expect(modelPicker).toHaveAttribute('aria-haspopup', 'true');
    expect(modelPicker).toHaveAttribute('aria-expanded', 'false');
  });

  it('FloatingChatLayout Clear Input button has aria-label and title', () => {
    render(<ChatLayoutTemplates {...baseProps} layout="floating" />);
    const clearButton = screen.getByRole('button', { name: /Clear conversation/i });
    expect(clearButton).toHaveAttribute('aria-label', 'Clear conversation');
    expect(clearButton).toHaveAttribute('title', 'Clear conversation');
  });

  it('TerminalChatLayout Send button has aria-label and title', () => {
    render(<ChatLayoutTemplates {...baseProps} layout="terminal" />);
    const sendButton = screen.getByRole('button', { name: /Senden/i });
    expect(sendButton).toHaveAttribute('aria-label', 'Senden');
    expect(sendButton).toHaveAttribute('title', 'Senden');
  });

  it('SplitViewLayout Send button has aria-label and title', () => {
    render(<ChatLayoutTemplates {...baseProps} layout="split-view" />);
    const sendButton = screen.getByRole('button', { name: /Senden/i });
    expect(sendButton).toHaveAttribute('aria-label', 'Senden');
    expect(sendButton).toHaveAttribute('title', 'Senden');
  });
});
