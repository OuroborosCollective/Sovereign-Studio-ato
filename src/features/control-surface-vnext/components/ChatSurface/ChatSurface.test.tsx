import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ChatSurface } from './ChatSurface';

vi.mock('../../utils/audio', () => ({
  playDispatchBlast: vi.fn(),
  playKeystrokeChirp: vi.fn(),
}));

const baseProps = {
  onOpenToolchain: vi.fn(),
  onOpenSkills: vi.fn(),
  onOpenIntegrations: vi.fn(),
  onTypingStateChange: vi.fn(),
};

describe('ChatSurface advisory/execution boundary', () => {
  it('sends composer text only to chat and starts an order only from the selected message', () => {
    const onSendMessage = vi.fn();
    const onSubmitOrder = vi.fn();
    render(
      <ChatSurface
        {...baseProps}
        messages={[{
          id: 'user-1',
          role: 'human',
          sender: 'HUMAN',
          content: 'Erkläre mir die Architektur.',
          timestamp: '2026-09-22T12:00:00.000Z',
        }]}
        onSendMessage={onSendMessage}
        onSubmitOrder={onSubmitOrder}
      />,
    );

    fireEvent.change(screen.getByTestId('mission__textarea'), { target: { value: 'Kannst du mich beraten?' } });
    fireEvent.click(screen.getByRole('button', { name: 'SEND' }));
    expect(onSendMessage).toHaveBeenCalledWith('Kannst du mich beraten?');
    expect(onSubmitOrder).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Nachrichtenaktionen' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Auftrag starten' }));
    expect(onSubmitOrder).toHaveBeenCalledWith('Erkläre mir die Architektur.');
  });

  it('keeps chat sendable during execution but disables explicit order actions', () => {
    const onSendMessage = vi.fn();
    const onSubmitOrder = vi.fn();
    render(
      <ChatSurface
        {...baseProps}
        messages={[{
          id: 'user-1',
          role: 'human',
          sender: 'HUMAN',
          content: 'Status bitte.',
          timestamp: '2026-09-22T12:00:00.000Z',
        }]}
        jobPhase="EXECUTING"
        onSendMessage={onSendMessage}
        onSubmitOrder={onSubmitOrder}
      />,
    );

    fireEvent.change(screen.getByTestId('mission__textarea'), { target: { value: 'Wie weit ist der Auftrag?' } });
    fireEvent.click(screen.getByRole('button', { name: 'SEND' }));
    expect(onSendMessage).toHaveBeenCalledWith('Wie weit ist der Auftrag?');

    fireEvent.click(screen.getByRole('button', { name: 'Nachrichtenaktionen' }));
    expect(screen.getByRole('menuitem', { name: 'Auftrag starten' })).toBeDisabled();
  });
});
