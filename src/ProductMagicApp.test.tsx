// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react';
import { Provider } from 'react-redux';

// --- Mocks -----------------------------------------------------------------

// Avoid touching Capacitor Preferences / localStorage; report no saved keys.
vi.mock('./features/ai/keyStorage', () => ({
  keyStorage: {
    get: vi.fn(async (_key: string, fallback = '') => fallback),
    set: vi.fn(async () => {}),
    remove: vi.fn(async () => {}),
    onSaved: vi.fn(() => () => {}),
  },
}));

// Gemini SDK calls are mocked so we can deterministically force failures.
const generateTextMock = vi.fn();
vi.mock('./features/ai/geminiService', () => ({
  geminiService: {
    generateText: (...args: unknown[]) => generateTextMock(...args),
  },
}));

// Free-provider fallback calls are mocked so "all providers fail" is reproducible.
const callGroqMock = vi.fn();
const callHuggingFaceMock = vi.fn();
const callTogetherMock = vi.fn();
const callOpenRouterMock = vi.fn();
vi.mock('./features/ai/providerManager', () => ({
  FREE_PROVIDERS: [],
  providerManager: {
    setApiKey: vi.fn(),
    getConfiguredProviders: vi.fn(() => []),
    generateWithFallback: vi.fn(),
  },
  callGroq: (...args: unknown[]) => callGroqMock(...args),
  callHuggingFace: (...args: unknown[]) => callHuggingFaceMock(...args),
  callTogether: (...args: unknown[]) => callTogetherMock(...args),
  callOpenRouter: (...args: unknown[]) => callOpenRouterMock(...args),
}));

import ProductMagicApp from './ProductMagicApp';
import { store } from './store';

const BANNER_HEADING = 'Alle AI-Provider nicht verfügbar';

function renderApp() {
  return render(
    <Provider store={store}>
      <ProductMagicApp />
    </Provider>
  );
}

// Wait out the on-mount async key load so state has settled before asserting.
async function flushMount() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('ProductMagicApp — all AI providers unavailable banner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom does not implement scrollIntoView (used by focusKeyInput).
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the red recovery banner when "Produkt bauen" runs with no keys', async () => {
    renderApp();
    await flushMount();

    // No banner before the user does anything.
    expect(screen.queryByText(BANNER_HEADING)).not.toBeInTheDocument();

    const buildButton = screen.getByRole('button', { name: /Produkt bauen/i });
    fireEvent.click(buildButton);

    expect(await screen.findByText(BANNER_HEADING)).toBeInTheDocument();
    expect(
      screen.getByText(/Kein API-Key konfiguriert/i)
    ).toBeInTheDocument();
  });

  it('clears the banner when a key is entered, and the CTA focuses the Gemini input', async () => {
    renderApp();
    await flushMount();

    // Trigger the banner first.
    fireEvent.click(screen.getByRole('button', { name: /Produkt bauen/i }));
    expect(await screen.findByText(BANNER_HEADING)).toBeInTheDocument();

    // The CTA inside the banner should focus the Gemini key input.
    const ctaButton = screen.getByRole('button', { name: /API-Key eintragen/i });
    const geminiInput = screen.getByPlaceholderText('AIza...') as HTMLInputElement;

    fireEvent.click(ctaButton);
    expect(document.activeElement).toBe(geminiInput);

    // Clicking the CTA also dismisses the banner; re-trigger it, then type a key.
    fireEvent.click(screen.getByRole('button', { name: /Produkt bauen/i }));
    expect(await screen.findByText(BANNER_HEADING)).toBeInTheDocument();

    fireEvent.change(geminiInput, { target: { value: 'AIza-test-key' } });

    await waitFor(() => {
      expect(screen.queryByText(BANNER_HEADING)).not.toBeInTheDocument();
    });
  });

  it('shows the banner when all providers throw during a build', async () => {
    // Force every provider to fail. Gemini throws a retryable (quota) error so the
    // fallback chain runs, and each free provider rejects too.
    generateTextMock.mockRejectedValue(new Error('429 quota exceeded'));
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callHuggingFaceMock.mockRejectedValue(new Error('hf down'));
    callTogetherMock.mockRejectedValue(new Error('together down'));
    callOpenRouterMock.mockRejectedValue(new Error('openrouter down'));

    renderApp();
    await flushMount();

    // Configure every provider with a key so the full fallback chain is exercised.
    fireEvent.change(screen.getByPlaceholderText('AIza...'), { target: { value: 'AIza-key' } });
    fireEvent.change(screen.getByPlaceholderText('gsk_...'), { target: { value: 'gsk_key' } });
    fireEvent.change(screen.getByPlaceholderText('hf_...'), { target: { value: 'hf_key' } });
    fireEvent.change(screen.getByPlaceholderText('...'), { target: { value: 'together_key' } });
    fireEvent.change(screen.getByPlaceholderText('sk-or-...'), { target: { value: 'sk-or-key' } });

    fireEvent.click(screen.getByRole('button', { name: /Produkt bauen/i }));

    expect(await screen.findByText(BANNER_HEADING)).toBeInTheDocument();
    expect(
      screen.getByText(/Alle AI-Provider sind fehlgeschlagen/i)
    ).toBeInTheDocument();

    // Confirm the fallback chain was actually walked end-to-end.
    await waitFor(() => {
      expect(generateTextMock).toHaveBeenCalled();
      expect(callGroqMock).toHaveBeenCalled();
      expect(callHuggingFaceMock).toHaveBeenCalled();
      expect(callTogetherMock).toHaveBeenCalled();
      expect(callOpenRouterMock).toHaveBeenCalled();
    });
  });
});
