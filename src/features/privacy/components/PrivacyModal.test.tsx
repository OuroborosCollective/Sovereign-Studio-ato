// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { PrivacyModal } from './PrivacyModal';

describe('PrivacyModal', () => {
  afterEach(cleanup);

  it('binds the policy to the exact Google Play app and developer identity', () => {
    render(<PrivacyModal isOpen onClose={vi.fn()} />);

    expect(screen.getByText('ARE-LOGIK - NOCode Studio')).toBeDefined();
    expect(screen.getByText('com.arestudio.nocode.aab')).toBeDefined();
    expect(screen.getByText('ARE-LOGIC ENGINE')).toBeDefined();
    expect(screen.getByText('Susanne Möller')).toBeDefined();
    expect(screen.getByRole('link', { name: '/privacy.html' })).toHaveAttribute('href', '/privacy.html');
  });

  it('closes from the explicit close action', () => {
    const onClose = vi.fn();
    render(<PrivacyModal isOpen onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
