import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaywallModal from '../PaywallModal';

describe('PaywallModal', () => {
  it('calls onSubscribe with the correct plan id when a subscribe button is clicked', async () => {
    const onSubscribeMock = vi.fn();
    const onCloseMock = vi.fn();

    render(
      <PaywallModal show={true} onClose={onCloseMock} onSubscribe={onSubscribeMock} />
    );

    const basicButton = screen.getByText('Kostenlos starten');
    const proButton = screen.getByText('Jetzt upgraden');
    const enterpriseButton = screen.getByText('Kontakt aufnehmen');

    const user = userEvent.setup();

    await user.click(basicButton);
    expect(onSubscribeMock).toHaveBeenCalledWith('basic');

    await user.click(proButton);
    expect(onSubscribeMock).toHaveBeenCalledWith('pro');

    await user.click(enterpriseButton);
    expect(onSubscribeMock).toHaveBeenCalledWith('enterprise');

    expect(onSubscribeMock).toHaveBeenCalledTimes(3);
  });

  it('does not render the modal when show is false', () => {
    const onSubscribeMock = vi.fn();
    const onCloseMock = vi.fn();

    const { container } = render(
      <PaywallModal show={false} onClose={onCloseMock} onSubscribe={onSubscribeMock} />
    );

    expect(container.firstChild).toBeNull();
  });

  it('calls onClose when the close button is clicked', async () => {
    const onSubscribeMock = vi.fn();
    const onCloseMock = vi.fn();

    render(
      <PaywallModal show={true} onClose={onCloseMock} onSubscribe={onSubscribeMock} />
    );

    // The close button has no text but has an X icon. We can find it by its generic role or structure.
    // It's the only button in the modal header
    const closeButton = screen.getAllByRole('button')[0]; // The close button is the first button rendered

    const user = userEvent.setup();
    await user.click(closeButton);

    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when the backdrop is clicked', async () => {
    const onSubscribeMock = vi.fn();
    const onCloseMock = vi.fn();

    const { container } = render(
      <PaywallModal show={true} onClose={onCloseMock} onSubscribe={onSubscribeMock} />
    );

    // The backdrop is the first child div with absolute positioning
    const backdrop = container.querySelector('.bg-black\\/60');

    if (!backdrop) {
      throw new Error('Backdrop not found');
    }

    const user = userEvent.setup();
    await user.click(backdrop);

    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});