import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { ChatSurface } from './ChatSurface';

const baseProps = {
  messages: [{
    id: 'assistant-1',
    role: 'assistant' as const,
    content: 'Exakte Nachricht mit Repository-Arbeit.',
    timestamp: '2026-09-22T10:00:00.000Z',
  }],
  onOpenToolchain: vi.fn(),
  onOpenSkills: vi.fn(),
  onOpenIntegrations: vi.fn(),
};

describe('ChatSurface', () => {
  it('routes the composer only to advisory chat and never to explicit order execution', () => {
    const onSendMessage = vi.fn();
    const onSubmitOrder = vi.fn();
    const view = render(<ChatSurface {...baseProps} onSendMessage={onSendMessage} onSubmitOrder={onSubmitOrder} />);

    const textarea = view.getByTestId('mission__textarea');
    fireEvent.change(textarea, { target: { value: 'Bitte erkläre die Architektur.' } });
    fireEvent.click(view.getByTestId('chat__send'));

    expect(onSendMessage).toHaveBeenCalledWith('Bitte erkläre die Architektur.');
    expect(onSubmitOrder).not.toHaveBeenCalled();
  });

  it('keeps advisory chat usable while a repository execution is active', () => {
    const onSendMessage = vi.fn();
    const view = render(
      <ChatSurface
        {...baseProps}
        jobPhase="EXECUTING"
        onSendMessage={onSendMessage}
      />,
    );

    fireEvent.change(view.getByTestId('mission__textarea'), { target: { value: 'Wie ist der Lauf?' } });
    fireEvent.click(view.getByTestId('chat__send'));

    expect(onSendMessage).toHaveBeenCalledWith('Wie ist der Lauf?');
  });

  it('passes the exact stored message content through the visible order action', () => {
    const onSubmitOrder = vi.fn();
    const view = render(<ChatSurface {...baseProps} onSubmitOrder={onSubmitOrder} />);

    fireEvent.click(view.getByTestId('message-actions-assistant-1'));
    fireEvent.click(view.getByTestId('message-order-assistant-1'));

    expect(onSubmitOrder).toHaveBeenCalledTimes(1);
    expect(onSubmitOrder).toHaveBeenCalledWith('Exakte Nachricht mit Repository-Arbeit.');
  });

  it('disables explicit order action during an active execution', () => {
    const onSubmitOrder = vi.fn();
    const view = render(<ChatSurface {...baseProps} onSubmitOrder={onSubmitOrder} jobPhase="EXECUTING" />);

    fireEvent.click(view.getByTestId('message-actions-assistant-1'));
    expect(view.getByTestId('message-order-assistant-1')).toBeDisabled();

    fireEvent.click(view.getByTestId('message-order-assistant-1'));
    expect(onSubmitOrder).not.toHaveBeenCalled();
  });
});
