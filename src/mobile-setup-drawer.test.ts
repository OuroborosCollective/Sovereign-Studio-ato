import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const DRAWER_ID = 'sovereign-mobile-setup-drawer';
const STYLE_ID = 'sovereign-mobile-setup-style';
const STORAGE_KEY = 'sovereign-mobile-setup-draft';
const INSTALL_FLAG = '__sovereignMobileSetupDrawerInstalled';

type DrawerModule = typeof import('./mobile-setup-drawer');

function setupRepoDom(loadText = '1 · Load Repo'): HTMLButtonElement {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <div><button type="button">Repo</button></div>
        <section>
          <input aria-label="GitHub Repository URL" />
          <input aria-label="GitHub private access" />
          <button type="button">${loadText}</button>
        </section>
      </div>
    </div>
  `;

  return getLoadButton(loadText);
}

function setupRepoDomWithoutInputs(): void {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <div><button type="button">Repo</button></div>
        <section data-role="repo-section"></section>
      </div>
    </div>
  `;
}

function appendRepoInputsAndLoadButton(loadText = '1 · Load Repo'): HTMLButtonElement {
  const section = document.querySelector('[data-role="repo-section"]') ?? document.body;

  section.insertAdjacentHTML(
    'beforeend',
    `
      <input aria-label="GitHub Repository URL" />
      <input aria-label="GitHub private access" />
      <button type="button">${loadText}</button>
    `,
  );

  return getLoadButton(loadText);
}

function getLoadButton(loadText = '1 · Load Repo'): HTMLButtonElement {
  const loadButton = Array.from(document.querySelectorAll('button')).find((button) =>
    button.textContent?.includes(loadText),
  );

  if (!(loadButton instanceof HTMLButtonElement)) {
    throw new Error(`expected load button "${loadText}" to exist`);
  }

  return loadButton;
}

async function loadDrawerModule(): Promise<DrawerModule> {
  vi.resetModules();
  return import('./mobile-setup-drawer');
}

function clearInstallFlag(): void {
  delete (window as Window & typeof globalThis & Record<string, unknown>)[INSTALL_FLAG];
}

function getDrawerRoot(): HTMLElement {
  const root = document.getElementById(DRAWER_ID);

  if (!root) {
    throw new Error('expected setup drawer root to exist');
  }

  return root;
}

function getDrawerInput(field: 'repoUrl' | 'accessValue'): HTMLInputElement {
  const input = getDrawerRoot().querySelector<HTMLInputElement>(`[data-field="${field}"]`);

  if (!input) {
    throw new Error(`expected drawer input ${field} to exist`);
  }

  return input;
}

function getSaveButton(): HTMLButtonElement {
  const button = Array.from(getDrawerRoot().querySelectorAll('button')).find(
    (candidate) => candidate.textContent === 'Speichern & Repo',
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error('expected save button to exist');
  }

  return button;
}

function getFabButton(): HTMLButtonElement {
  const button = getDrawerRoot().querySelector<HTMLButtonElement>('.setup-fab');

  if (!button) {
    throw new Error('expected setup fab button to exist');
  }

  return button;
}

function getPanel(): HTMLElement {
  const panel = getDrawerRoot().querySelector<HTMLElement>('.setup-panel');

  if (!panel) {
    throw new Error('expected setup panel to exist');
  }

  return panel;
}

function getStatus(): HTMLElement {
  const status = getDrawerRoot().querySelector<HTMLElement>('[data-role="setup-status"]');

  if (!status) {
    throw new Error('expected setup status to exist');
  }

  return status;
}

function getRepoInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[aria-label="GitHub Repository URL"]');

  if (!input) {
    throw new Error('expected repo input to exist');
  }

  return input;
}

function getAccessInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[aria-label="GitHub private access"]');

  if (!input) {
    throw new Error('expected access input to exist');
  }

  return input;
}

function getRepoButton(): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === 'Repo',
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error('expected Repo button to exist');
  }

  return button;
}

function setDrawerValues(repoUrl: string, accessValue: string): void {
  getDrawerInput('repoUrl').value = repoUrl;
  getDrawerInput('accessValue').value = accessValue;
}

function readSavedDraft(): unknown {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw ? JSON.parse(raw) : null;
}

function appendBodyMarker(text: string): void {
  const marker = document.createElement('div');
  marker.textContent = text;
  document.body.appendChild(marker);
}

function installAndRender(installMobileSetupDrawer: () => void): void {
  installMobileSetupDrawer();
  vi.advanceTimersByTime(901);
}

describe('mobile setup drawer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    clearInstallFlag();
    window.localStorage.clear();
    document.head.innerHTML = '';
    setupRepoDom();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    clearInstallFlag();
    window.localStorage.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('renders the drawer and style after installation delay', async () => {
    const { installMobileSetupDrawer } = await loadDrawerModule();

    installMobileSetupDrawer();

    expect(document.getElementById(DRAWER_ID)).toBeNull();

    vi.advanceTimersByTime(901);

    expect(document.getElementById(DRAWER_ID)).toBeDefined();
    expect(document.getElementById(STYLE_ID)).toBeDefined();
    expect(getDrawerInput('repoUrl')).toBeInstanceOf(HTMLInputElement);
    expect(getDrawerInput('accessValue')).toBeInstanceOf(HTMLInputElement);
    expect(getStatus().textContent).toBe('Bereit.');
  });

  it('toggles the panel without losing input state', async () => {
    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    const panel = getPanel();
    const fab = getFabButton();

    expect(panel.classList.contains('hidden')).toBe(true);

    fab.click();
    expect(panel.classList.contains('hidden')).toBe(false);

    setDrawerValues('https://github.com/owner/repo', 'ram-secret');

    fab.click();
    expect(panel.classList.contains('hidden')).toBe(true);

    fab.click();
    expect(panel.classList.contains('hidden')).toBe(false);
    expect(getDrawerInput('repoUrl').value).toBe('https://github.com/owner/repo');
    expect(getDrawerInput('accessValue').value).toBe('ram-secret');
  });

  it('is visually idempotent when installed repeatedly', async () => {
    const { installMobileSetupDrawer } = await loadDrawerModule();

    installMobileSetupDrawer();
    installMobileSetupDrawer();
    installMobileSetupDrawer();

    vi.advanceTimersByTime(901);

    expect(document.querySelectorAll(`#${DRAWER_ID}`)).toHaveLength(1);
    expect(document.querySelectorAll(`#${STYLE_ID}`)).toHaveLength(1);

    installMobileSetupDrawer();
    vi.advanceTimersByTime(901);

    expect(document.querySelectorAll(`#${DRAWER_ID}`)).toHaveLength(1);
    expect(document.querySelectorAll(`#${STYLE_ID}`)).toHaveLength(1);
  });

  it('can reinstall if the drawer root was removed by an app shell rerender', async () => {
    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    expect(document.getElementById(DRAWER_ID)).toBeDefined();

    document.getElementById(DRAWER_ID)?.remove();

    expect(document.getElementById(DRAWER_ID)).toBeNull();

    installMobileSetupDrawer();
    vi.advanceTimersByTime(901);

    expect(document.getElementById(DRAWER_ID)).toBeDefined();
    expect(document.querySelectorAll(`#${DRAWER_ID}`)).toHaveLength(1);
    expect(document.querySelectorAll(`#${STYLE_ID}`)).toHaveLength(1);
  });

  it('restores only the repo URL draft and never restores private access', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        repoUrl: '  https://github.com/owner/repo  ',
        accessValue: 'should-not-restore',
      }),
    );

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    expect(getDrawerInput('repoUrl').value).toBe('https://github.com/owner/repo');
    expect(getDrawerInput('accessValue').value).toBe('');
  });

  it('survives malformed localStorage draft data', async () => {
    window.localStorage.setItem(STORAGE_KEY, '{not-json');

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    expect(getDrawerInput('repoUrl').value).toBe('');
    expect(getDrawerInput('accessValue').value).toBe('');
    expect(getStatus().textContent).toBe('Bereit.');
  });

  it('applies values and clicks Load Repo after save', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn(() => {
      appendBodyMarker('echte repo-einträge geladen');
    });

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(2200);

    expect(getRepoInput().value).toBe('https://github.com/owner/repo');
    expect(getAccessInput().value).toBe('private-access-value');
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('loaded');
    expect(getStatus().textContent).toBe('Repository load completed.');
  });

  it('clicks the Repo tab before applying values', async () => {
    const repoButton = getRepoButton();
    const loadButton = getLoadButton();
    const onRepoClick = vi.fn();
    const onLoad = vi.fn(() => {
      appendBodyMarker('repository loaded');
    });

    repoButton.addEventListener('click', onRepoClick);
    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(2200);

    expect(onRepoClick).toHaveBeenCalledTimes(1);
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('loaded');
  });

  it('does not persist private access in localStorage', async () => {
    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'super-private-access-value');
    getSaveButton().click();

    const rawDraft = window.localStorage.getItem(STORAGE_KEY);
    const savedDraft = readSavedDraft();

    expect(rawDraft).not.toContain('super-private-access-value');
    expect(savedDraft).toEqual({
      repoUrl: 'https://github.com/owner/repo',
    });
  });

  it('does not restore private access after a completed session rerender', async () => {
    const loadButton = getLoadButton();
    const onLoad = vi.fn(() => {
      appendBodyMarker('repository loaded');
    });

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'one-run-access');
    getSaveButton().click();

    vi.advanceTimersByTime(2200);

    expect(getStatus().dataset.phase).toBe('loaded');

    document.getElementById(DRAWER_ID)?.remove();

    installMobileSetupDrawer();
    vi.advanceTimersByTime(901);

    expect(getDrawerInput('repoUrl').value).toBe('https://github.com/owner/repo');
    expect(getDrawerInput('accessValue').value).toBe('');
  });

  it('rejects missing repo URL without clicking Load Repo', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn();

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(2000);

    expect(onLoad).not.toHaveBeenCalled();
    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toContain('GitHub Repository URL fehlt');
  });

  it('rejects invalid repo URL without clicking Load Repo', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn();

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('not-a-url', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(2000);

    expect(onLoad).not.toHaveBeenCalled();
    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toContain('GitHub Repository URL ist ungueltig');
  });

  it('rejects non-http repo URL without clicking Load Repo', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn();

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('ftp://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(2000);

    expect(onLoad).not.toHaveBeenCalled();
    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toContain('GitHub Repository URL muss http oder https nutzen');
  });

  it('waits for delayed Repo tab inputs before applying values', async () => {
    setupRepoDomWithoutInputs();

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'late-access');
    getSaveButton().click();

    vi.advanceTimersByTime(500);

    const loadButton = appendRepoInputsAndLoadButton();
    const onLoad = vi.fn(() => {
      appendBodyMarker('repo snapshot ready');
    });

    loadButton.addEventListener('click', onLoad);

    vi.advanceTimersByTime(5000);

    expect(getRepoInput().value).toBe('https://github.com/owner/repo');
    expect(getAccessInput().value).toBe('late-access');
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('loaded');
  });

  it('waits for disabled Load Repo button and clicks when it becomes enabled', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn(() => {
      appendBodyMarker('repo geladen');
    });

    loadButton.disabled = true;
    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(400);

    expect(onLoad).not.toHaveBeenCalled();
    expect(getStatus().textContent).toContain('Waiting for repository load button');

    loadButton.disabled = false;

    vi.advanceTimersByTime(3000);

    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('loaded');
  });

  it('marks session failed when repo URL input is unavailable after retries', async () => {
    setupRepoDomWithoutInputs();

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(12000);

    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toContain('Repo URL input was not found');
  });

  it('marks session failed when repo load button is unavailable', async () => {
    document.body.innerHTML = `
      <div id="root">
        <div class="min-h-screen">
          <div><button type="button">Repo</button></div>
          <section>
            <input aria-label="GitHub Repository URL" />
            <input aria-label="GitHub private access" />
          </section>
        </div>
      </div>
    `;

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(12000);

    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toContain(
      'Repository load button was not found or remained disabled',
    );
  });

  it('marks session failed when repo load outcome is not detected', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn();

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(45000);

    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toContain('Repository load outcome was not detected');
  });

  it('old pending session timers do not overwrite a newer setup submission', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn();

    loadButton.disabled = true;
    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/old-repo', 'old-access');
    getSaveButton().click();

    vi.advanceTimersByTime(500);

    expect(getRepoInput().value).toBe('https://github.com/owner/old-repo');
    expect(onLoad).not.toHaveBeenCalled();

    setDrawerValues('https://github.com/owner/new-repo', 'new-access');

    loadButton.disabled = false;
    loadButton.addEventListener('click', () => {
      appendBodyMarker('repository loaded');
    });

    getSaveButton().click();

    vi.advanceTimersByTime(5000);

    expect(getRepoInput().value).toBe('https://github.com/owner/new-repo');
    expect(getAccessInput().value).toBe('new-access');
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('loaded');
    expect(getStatus().textContent).toBe('Repository load completed.');
  });

  it('old delayed failure cannot overwrite a newer loaded session', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn();

    loadButton.disabled = true;
    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/old-repo', 'old-access');
    getSaveButton().click();

    vi.advanceTimersByTime(1000);

    loadButton.disabled = false;

    setDrawerValues('https://github.com/owner/new-repo', 'new-access');
    loadButton.addEventListener('click', () => {
      appendBodyMarker('repository loaded');
    });

    getSaveButton().click();

    vi.advanceTimersByTime(6000);

    expect(getRepoInput().value).toBe('https://github.com/owner/new-repo');
    expect(getStatus().dataset.phase).toBe('loaded');

    vi.advanceTimersByTime(60000);

    expect(getStatus().dataset.phase).toBe('loaded');
    expect(getStatus().textContent).toBe('Repository load completed.');
  });

  it('detects visible failure text after clicking Load Repo', async () => {
    const loadButton = setupRepoDom();
    const onLoad = vi.fn(() => {
      appendBodyMarker('repository nicht gefunden');
    });

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    setDrawerValues('https://github.com/owner/missing-repo', 'private-access-value');
    getSaveButton().click();

    vi.advanceTimersByTime(2200);

    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getStatus().dataset.phase).toBe('failed');
    expect(getStatus().textContent).toBe('Repository load failed.');
  });

  it('keeps existing DOM safe from injected drawer input markup', async () => {
    const { installMobileSetupDrawer } = await loadDrawerModule();

    installAndRender(installMobileSetupDrawer);

    const injected = `https://github.com/owner/repo"><img src=x onerror=alert(1)>`;

    setDrawerValues(injected, 'private-access-value');
    getSaveButton().click();

    expect(document.querySelectorAll(`#${DRAWER_ID} img`)).toHaveLength(0);
    expect(window.localStorage.getItem(STORAGE_KEY)).toContain(
      'https://github.com/owner/repo',
    );
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toContain('private-access-value');
  });
});
