import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const DRAWER_ID = 'sovereign-mobile-setup-drawer';
const STORAGE_KEY = 'sovereign-mobile-setup-draft';
const INSTALL_FLAG = '__sovereignMobileSetupDrawerInstalled';

type DrawerModule = typeof import('./mobile-setup-drawer');

async function loadDrawerModule(): Promise<DrawerModule> {
  vi.resetModules();
  return import('./mobile-setup-drawer');
}

function clearInstallFlag(): void {
  delete (window as Window & typeof globalThis & Record<string, unknown>)[INSTALL_FLAG];
}

function getDrawerInput(field: 'repoUrl' | 'accessValue'): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>(`#${DRAWER_ID} [data-field="${field}"]`);
  if (!input) throw new Error(`expected drawer input ${field}`);
  return input;
}

function getSaveButton(): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>(`#${DRAWER_ID} button`)).find(
    (item) => item.textContent === 'Speichern & Repo',
  );
  if (!button) throw new Error('expected save button');
  return button;
}

function getStatus(): HTMLElement {
  const status = document.querySelector<HTMLElement>(`#${DRAWER_ID} [data-role="setup-status"]`);
  if (!status) throw new Error('expected status');
  return status;
}

function installAndRender(installMobileSetupDrawer: () => void): void {
  installMobileSetupDrawer();
  vi.advanceTimersByTime(901);
}

describe('mobile setup drawer stable selectors', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    clearInstallFlag();
    window.localStorage.clear();
    document.head.innerHTML = '';
    document.body.innerHTML = `
      <div id="root">
        <button type="button">Repo</button>
        <section>
          <input data-testid="github-repo-url-input" name="github-repo-url" />
          <input data-testid="github-token-input" name="github-token" />
          <button type="button">1 · Load Repo</button>
        </section>
      </div>
    `;
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    clearInstallFlag();
    window.localStorage.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('applies drawer values through stable data-testid selectors when aria labels are absent', async () => {
    const loadButton = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
      button.textContent?.includes('Load Repo'),
    );
    const onLoad = vi.fn(() => {
      const marker = document.createElement('div');
      marker.textContent = 'repository loaded';
      document.body.appendChild(marker);
    });
    loadButton?.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();
    installAndRender(installMobileSetupDrawer);

    getDrawerInput('repoUrl').value = 'https://github.com/owner/repo';
    getDrawerInput('accessValue').value = 'token-value';
    getSaveButton().click();

    vi.advanceTimersByTime(2200);

    expect(document.querySelector<HTMLInputElement>('[data-testid="github-repo-url-input"]')?.value).toBe('https://github.com/owner/repo');
    expect(document.querySelector<HTMLInputElement>('[data-testid="github-token-input"]')?.value).toBe('token-value');
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('loaded');
    expect(getStatus().textContent).toBe('Repository load completed.');
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toContain('token-value');
  });
});
