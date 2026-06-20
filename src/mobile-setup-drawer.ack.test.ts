import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ROOT_ID = 'sovereign-mobile-setup-drawer';
const INSTALL_FLAG = '__sovereignMobileSetupDrawerInstalled';
const EVENT_NAME = 'sovereign:mobile-repo-setup';

type Mod = typeof import('./mobile-setup-drawer');
type AckWindow = Window & typeof globalThis & { __sovereignMobileRepoSetupAck?: string };

async function loadMod(): Promise<Mod> {
  vi.resetModules();
  return import('./mobile-setup-drawer');
}

function resetWin(): void {
  delete (window as Window & typeof globalThis & Record<string, unknown>)[INSTALL_FLAG];
  delete (window as AckWindow).__sovereignMobileRepoSetupAck;
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

describe('mobile setup ack fallback', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetWin();
    window.localStorage.clear();
    document.head.innerHTML = '';
    document.body.innerHTML = '<div id="root"><button type="button">Repo</button></div>';
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    resetWin();
    window.localStorage.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('does not render the missing field error after synchronous app acknowledgement', async () => {
    window.addEventListener(EVENT_NAME, (event) => {
      const detail = (event as CustomEvent<{ requestId: string }>).detail;
      (window as AckWindow).__sovereignMobileRepoSetupAck = detail.requestId;
      const marker = document.createElement('div');
      marker.textContent = 'repository loaded';
      document.body.appendChild(marker);
    });

    const { installMobileSetupDrawer } = await loadMod();
    installMobileSetupDrawer();
    vi.advanceTimersByTime(901);

    drawerInput('repoUrl').value = 'https://github.com/owner/repo';
    saveButton().click();

    vi.advanceTimersByTime(12_000);

    expect(statusNode().dataset.phase).toBe('loaded');
    expect(statusNode().textContent).toBe('Repository load completed.');
    expect(statusNode().textContent).not.toContain('Repo URL input was not found');
  });
});
