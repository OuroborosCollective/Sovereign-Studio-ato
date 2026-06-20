import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ROOT_ID = 'sovereign-mobile-setup-drawer';
const INSTALL_FLAG = '__sovereignMobileSetupDrawerInstalled';
const SNAPSHOT_KEY = 'sovereign-studio.repo-snapshot.v1';

type Mod = typeof import('./mobile-setup-drawer');
type MobileTestWindow = Window & typeof globalThis & { Capacitor?: unknown };

async function loadMod(): Promise<Mod> {
  vi.resetModules();
  return import('./mobile-setup-drawer');
}

function resetWin(): void {
  delete (window as Window & typeof globalThis & Record<string, unknown>)[INSTALL_FLAG];
  delete (window as MobileTestWindow).Capacitor;
}

function drawerInput(field: 'repoUrl' | 'accessValue'): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>(`#${ROOT_ID} [data-field="${field}"]`);
  if (!input) throw new Error(`missing drawer field ${field}`);
  return input;
}

function saveButton(): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>(`#${ROOT_ID} button`)).find(
    (item) => item.textContent === 'Speichern & Repo',
  );
  if (!button) throw new Error('missing save button');
  return button;
}

function statusNode(): HTMLElement {
  const status = document.querySelector<HTMLElement>(`#${ROOT_ID} [data-role="setup-status"]`);
  if (!status) throw new Error('missing status');
  return status;
}

describe('mobile setup drawer direct fallback', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetWin();
    window.localStorage.clear();
    document.head.innerHTML = '';
    document.body.innerHTML = '<div id="root"><button type="button">Repo</button></div>';
    (window as MobileTestWindow).Capacitor = { platform: 'android' };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/git/trees/')) {
        return {
          ok: true,
          json: async () => ({ tree: [{ path: 'README.md', type: 'blob', size: 12 }] }),
        };
      }
      return {
        ok: true,
        json: async () => ({ default_branch: 'main' }),
      };
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllTimers();
    vi.useRealTimers();
    resetWin();
    window.localStorage.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('loads and persists a durable repo snapshot when app inputs are unavailable on mobile runtime', async () => {
    const { installMobileSetupDrawer } = await loadMod();
    installMobileSetupDrawer();
    vi.advanceTimersByTime(901);

    drawerInput('repoUrl').value = 'https://github.com/owner/repo';
    saveButton().click();

    await vi.advanceTimersByTimeAsync(12_000);

    expect(statusNode().dataset.phase).toBe('loaded');
    expect(statusNode().textContent).toBe('Repository load completed.');
    expect(statusNode().textContent).not.toContain('Repo URL input was not found');

    const snapshot = JSON.parse(window.localStorage.getItem(SNAPSHOT_KEY) ?? '{}') as { repoFiles?: unknown[]; repoUrl?: string };
    expect(snapshot.repoUrl).toBe('https://github.com/owner/repo');
    expect(snapshot.repoFiles).toHaveLength(1);
  });
});
