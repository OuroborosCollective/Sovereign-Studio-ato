// @vitest-environment jsdom

import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

beforeAll(() => {
  const cryptoMock = {
    randomUUID: () => 'test-uuid',
  };

  if (!globalThis.crypto) {
    Object.defineProperty(globalThis, 'crypto', {
      value: cryptoMock,
      configurable: true,
    });
    return;
  }

  if (!globalThis.crypto.randomUUID) {
    Object.defineProperty(globalThis.crypto, 'randomUUID', {
      value: cryptoMock.randomUUID,
      configurable: true,
    });
  }
});

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete window.__sovereignSetupState;
});

function openWorkspace(): void {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Sovereign Arbeitsfläche öffnen' }));
}

function openRepoTab(): void {
  fireEvent.click(screen.getByRole('tab', { name: 'Open Repo tab' }));
}

describe('App setup flow smoke', () => {
  it('keeps Full Auto blocked until a real repository snapshot exists', async () => {
    openWorkspace();

    const automationSelect = screen.getByTestId('automation__mode-select');
    fireEvent.change(automationSelect, { target: { value: 'full-auto-draft-pr' } });

    expect(await screen.findByText('Automation needs a loaded repository snapshot.')).toBeDefined();
  });

  it('publishes direct Repo access UI input into the setup bridge', async () => {
    const listener = vi.fn();
    window.addEventListener('sovereign:setup-state', listener);

    openWorkspace();
    openRepoTab();

    fireEvent.change(screen.getByPlaceholderText('https://github.com/owner/repository'), {
      target: { value: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato' },
    });
    fireEvent.change(screen.getByLabelText('GitHub private access'), {
      target: { value: 'access-value-for-test' },
    });

    await waitFor(() => {
      expect(window.__sovereignSetupState).toMatchObject({
        hasToken: true,
        tokenStatus: 'valid',
        repoReady: false,
        setupPhase: 'no-repo',
        isBusy: false,
      });
    });
    expect(listener).toHaveBeenCalled();

    window.removeEventListener('sovereign:setup-state', listener);
  });

  it('keeps Pattern Memory count visible in the monitor region', async () => {
    openWorkspace();

    const moreSelect = screen.getByTestId('tabbar__more-select');
    fireEvent.change(moreSelect, { target: { value: 'monitor' } });

    const monitor = await screen.findByTestId('operator-monitor');
    expect(within(monitor).getByText('Patterns: 0')).toBeDefined();
    expect(within(monitor).getByRole('heading', { name: 'Pattern Memory' })).toBeDefined();
  });
});
