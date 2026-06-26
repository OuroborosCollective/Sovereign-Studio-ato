import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const MORE_MENU_ID = 'sovereign-more-menu';
const COACH_ID = 'sovereign-mobile-coach';
const DRAWER_ID = 'sovereign-mobile-setup-drawer';
const SETUP_STORAGE_KEY = 'sovereign-mobile-setup-draft';
const SETUP_INSTALL_FLAG = '__sovereignMobileSetupDrawerInstalled';

type GuidanceModules = {
  installMobileMoreMenu: () => void;
  installMobileOperatorCoach: () => void;
  installMobileSetupDrawer: () => void;
};

function mountShell(extra = ''): void {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <h1>Sovereign Canvas Tool</h1>
        <div data-role="primary-nav">
          <button type="button">Repo</button>
          <button type="button">Builder</button>
          <button type="button">Files</button>
          <button type="button">Diff</button>
          <button type="button">Workflow</button>
          <button type="button">Repair</button>
          <button type="button">Remote Memory</button>
          <button type="button">Pattern Memory</button>
          <button type="button">Telemetry</button>
          <button type="button">Live Monitor</button>
        </div>
        <section data-role="repo-state">Repo fehlt. Noch kein echtes Repo geladen.</section>
        <section data-role="automation">
          <select aria-label="Automation Mode">
            <option value="manual">Manual</option>
            <option value="auto-review">Auto Review</option>
            <option value="full-auto-draft-pr">Full Auto Draft PR</option>
          </select>
        </section>
        <section data-role="repo-form">
          <label>GitHub Repository URL<input aria-label="GitHub Repository URL" /></label>
          <label>GitHub private access<input aria-label="GitHub private access" type="password" /></label>
          <button type="button">1 · Load Repo</button>
        </section>
        ${extra}
      </div>
    </div>
  `;
}

async function loadGuidanceModules(): Promise<GuidanceModules> {
  vi.resetModules();

  const [moreMenu, operatorCoach, setupDrawer] = await Promise.all([
    import('./mobile-more-menu'),
    import('./mobile-operator-coach'),
    import('./mobile-setup-drawer'),
  ]);

  return {
    installMobileMoreMenu: moreMenu.installMobileMoreMenu,
    installMobileOperatorCoach: operatorCoach.installMobileOperatorCoach,
    installMobileSetupDrawer: setupDrawer.installMobileSetupDrawer,
  };
}

function clearSetupInstallFlag(): void {
  delete (window as Window & typeof globalThis & Record<string, unknown>)[SETUP_INSTALL_FLAG];
}

function advanceInstallTimers(): void {
  vi.advanceTimersByTime(1200);
}

function buttonByText(label: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === label,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`expected button "${label}" to exist`);
  }

  return button;
}

function buttonContaining(label: string): HTMLButtonElement {
  const needle = label.toLowerCase();
  const button = Array.from(document.querySelectorAll('button')).find((candidate) =>
    (candidate.textContent ?? '').toLowerCase().includes(needle),
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`expected button containing "${label}" to exist`);
  }

  return button;
}

function selectByLabel(label: string): HTMLSelectElement {
  const select = document.querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`);

  if (!select) {
    throw new Error(`expected select "${label}" to exist`);
  }

  return select;
}

function inputByLabel(label: string): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);

  if (!input) {
    throw new Error(`expected input "${label}" to exist`);
  }

  return input;
}

function getCoach(): HTMLElement {
  const coach = document.getElementById(COACH_ID);

  if (!coach) {
    throw new Error('expected mobile operator coach to exist');
  }

  return coach;
}

function getDrawerRoot(): HTMLElement {
  const drawer = document.getElementById(DRAWER_ID);

  if (!drawer) {
    throw new Error('expected mobile setup drawer to exist');
  }

  return drawer;
}

function getDrawerInput(field: 'repoUrl' | 'accessValue'): HTMLInputElement {
  const input = getDrawerRoot().querySelector<HTMLInputElement>(`[data-field="${field}"]`);

  if (!input) {
    throw new Error(`expected drawer input ${field} to exist`);
  }

  return input;
}

function getDrawerSaveButton(): HTMLButtonElement {
  const button = Array.from(getDrawerRoot().querySelectorAll('button')).find(
    (candidate) => candidate.textContent === 'Speichern & Repo',
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error('expected setup drawer save button to exist');
  }

  return button;
}

function getDrawerFab(): HTMLButtonElement {
  const button = getDrawerRoot().querySelector<HTMLButtonElement>('.setup-fab');

  if (!button) {
    throw new Error('expected setup drawer fab to exist');
  }

  return button;
}

function getDrawerPanel(): HTMLElement {
  const panel = getDrawerRoot().querySelector<HTMLElement>('.setup-panel');

  if (!panel) {
    throw new Error('expected setup drawer panel to exist');
  }

  return panel;
}

function getDrawerStatus(): HTMLElement {
  const status = getDrawerRoot().querySelector<HTMLElement>('[data-role="setup-status"]');

  if (!status) {
    throw new Error('expected setup drawer status to exist');
  }

  return status;
}

function setDrawerValues(repoUrl: string, accessValue: string): void {
  getDrawerInput('repoUrl').value = repoUrl;
  getDrawerInput('accessValue').value = accessValue;
}

function expectVisibleButton(label: string): void {
  expect(buttonByText(label).style.display).not.toBe('none');
}

function expectHiddenButton(label: string): void {
  expect(buttonByText(label).style.display).toBe('none');
}

function expectTextContainsAny(source: string | null | undefined, needles: string[]): void {
  const text = source ?? '';

  expect(
    needles.some((needle) => text.includes(needle)),
    `expected text to contain one of: ${needles.join(' | ')}`,
  ).toBe(true);
}

function appendMarker(text: string): HTMLElement {
  const marker = document.createElement('section');
  marker.textContent = text;
  document.body.appendChild(marker);
  return marker;
}

function installAll(modules: GuidanceModules): void {
  modules.installMobileMoreMenu();
  modules.installMobileOperatorCoach();
  modules.installMobileSetupDrawer();
}

function expectSingleGuidanceRoots(): void {
  expect(document.querySelectorAll(`#${MORE_MENU_ID}`)).toHaveLength(1);
  expect(document.querySelectorAll(`#${COACH_ID}`)).toHaveLength(1);
  expect(document.querySelectorAll(`#${DRAWER_ID}`)).toHaveLength(1);
}

describe('mobile workflow guidance', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    clearSetupInstallFlag();
    window.localStorage.clear();
    document.head.innerHTML = '';
    mountShell();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    clearSetupInstallFlag();
    window.localStorage.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('moves secondary areas into a mobile more menu and keeps automation manual until user chooses', async () => {
    const { installMobileMoreMenu } = await loadGuidanceModules();

    installMobileMoreMenu();
    advanceInstallTimers();

    expect(document.getElementById(MORE_MENU_ID)).toBeTruthy();
    expect(selectByLabel('Mehr Bereiche')).toBeTruthy();

    expectVisibleButton('Repo');
    expectVisibleButton('Builder');
    expectVisibleButton('Files');
    expectVisibleButton('Diff');

    expectHiddenButton('Workflow');
    expectHiddenButton('Repair');
    expectHiddenButton('Remote Memory');
    expectHiddenButton('Pattern Memory');
    expectHiddenButton('Telemetry');
    expectHiddenButton('Live Monitor');

    expect(selectByLabel('Automation Mode').value).toBe('manual');
  });

  it('keeps mobile more menu installation idempotent', async () => {
    const { installMobileMoreMenu } = await loadGuidanceModules();

    installMobileMoreMenu();
    installMobileMoreMenu();
    installMobileMoreMenu();

    advanceInstallTimers();

    expect(document.querySelectorAll(`#${MORE_MENU_ID}`)).toHaveLength(1);
    expect(document.querySelectorAll('select[aria-label="Mehr Bereiche"]')).toHaveLength(1);
    expect(selectByLabel('Automation Mode').value).toBe('manual');
  });

  it('routes every secondary menu selection back through existing shell buttons', async () => {
    const secondaryLabels = [
      'Workflow',
      'Repair',
      'Remote Memory',
      'Pattern Memory',
      'Telemetry',
      'Live Monitor',
    ];

    const clicks = new Map<string, ReturnType<typeof vi.fn>>();

    for (const label of secondaryLabels) {
      const spy = vi.fn();
      clicks.set(label, spy);
      buttonByText(label).addEventListener('click', spy);
    }

    const { installMobileMoreMenu } = await loadGuidanceModules();

    installMobileMoreMenu();
    advanceInstallTimers();

    const select = selectByLabel('Mehr Bereiche');

    for (const label of secondaryLabels) {
      select.value = label;
      select.dispatchEvent(new Event('change', { bubbles: true }));

      expect(clicks.get(label)).toHaveBeenCalledTimes(1);
    }

    expectVisibleButton('Repo');
    expectVisibleButton('Builder');
    expectVisibleButton('Files');
    expectVisibleButton('Diff');
  });

  it('renders the operator coach inline after navigation with yellow setup guidance', async () => {
    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    const coach = getCoach();

    expect(coach.className).toContain('yellow');
    expect(coach.textContent).toContain('Sovereign Bot');
    expectTextContainsAny(coach.textContent, ['Repo Setup', 'Repo fehlt', 'Repository URL']);

    const nav = document.querySelector('[data-role="primary-nav"]');

    expect(nav?.nextElementSibling).toBe(coach);
  });

  it('keeps operator coach installation idempotent', async () => {
    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    installMobileOperatorCoach();
    installMobileOperatorCoach();

    advanceInstallTimers();

    expect(document.querySelectorAll(`#${COACH_ID}`)).toHaveLength(1);
    expect(getCoach().textContent).toContain('Sovereign Bot');
  });

  it('does not show a red stopper for harmless zero-failed runtime text', async () => {
    mountShell(
      '<section>Sequential Runtime Guard no active step; 0 completed step(s), 0 failed step(s). Runtime ready.</section>',
    );

    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    const coach = getCoach();

    expect(coach.className).not.toContain('red');
    expect(coach.textContent).not.toContain('Ich sehe einen echten Stopper');
  });

  it('shows red repair guidance for a real stopper', async () => {
    mountShell(
      '<section>Workflow failed. Package build failed with exit code 1. Critical blocker.</section>',
    );

    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    const coach = getCoach();

    expect(coach.className).toContain('red');
    expectTextContainsAny(coach.textContent, ['Stopper', 'Repair', 'Log']);
  });

  it('shows cautious review guidance when generated files passed self review', async () => {
    mountShell(
      '<section>Generated Files Review SELF REVIEW: ACCEPTED Generated package passed self review. Learning signal: generated-output-accepted</section>',
    );

    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    const coach = getCoach();

    expect(coach.className).toContain('yellow');
    expectTextContainsAny(coach.textContent, ['Ergebnis ist bereit', 'Ergebnis bereit', 'Files']);
  });

  it('shows cautious active work guidance for running workflow text', async () => {
    mountShell('<section>package-build running workflow-watch in progress</section>');

    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    const coach = getCoach();

    expect(coach.className).toContain('yellow');
    expectTextContainsAny(coach.textContent, ['Ich arbeite', 'Arbeitsmonitor', 'Live Monitor']);
  });

  it('keeps repo setup reachable from every tab through the global setup drawer', async () => {
    const loadButton = buttonContaining('Load Repo');
    const onLoad = vi.fn(() => {
      appendMarker('repository loaded');
    });

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadGuidanceModules();

    installMobileSetupDrawer();
    advanceInstallTimers();

    const root = getDrawerRoot();

    expect(root.textContent).toContain('Repo Setup');

    getDrawerFab().click();

    expect(getDrawerPanel().classList.contains('hidden')).toBe(false);

    setDrawerValues(
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      'secret-value',
    );

    getDrawerSaveButton().click();

    vi.advanceTimersByTime(3000);

    expect(inputByLabel('GitHub Repository URL').value).toBe(
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    );
    expect(inputByLabel('GitHub private access').value).toBe('secret-value');
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getDrawerStatus().dataset.phase).toBe('loaded');
  });

  it('does not persist private setup access while still applying it to the repo form', async () => {
    const loadButton = buttonContaining('Load Repo');

    loadButton.addEventListener('click', () => {
      appendMarker('repo geladen');
    });

    const { installMobileSetupDrawer } = await loadGuidanceModules();

    installMobileSetupDrawer();
    advanceInstallTimers();

    getDrawerFab().click();

    setDrawerValues('https://github.com/owner/repo', 'very-secret-value');
    getDrawerSaveButton().click();

    vi.advanceTimersByTime(3000);

    expect(inputByLabel('GitHub Repository URL').value).toBe('https://github.com/owner/repo');
    expect(inputByLabel('GitHub private access').value).toBe('very-secret-value');

    const rawDraft = window.localStorage.getItem(SETUP_STORAGE_KEY) ?? '';

    expect(rawDraft).toContain('https://github.com/owner/repo');
    expect(rawDraft).not.toContain('very-secret-value');
  });

  it('rejects invalid repo setup without triggering Load Repo', async () => {
    const loadButton = buttonContaining('Load Repo');
    const onLoad = vi.fn();

    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadGuidanceModules();

    installMobileSetupDrawer();
    advanceInstallTimers();

    getDrawerFab().click();

    setDrawerValues('not-a-url', 'secret-value');
    getDrawerSaveButton().click();

    vi.advanceTimersByTime(3000);

    expect(onLoad).not.toHaveBeenCalled();
    expect(getDrawerStatus().dataset.phase).toBe('failed');
    expect(getDrawerStatus().textContent).toContain('GitHub Repository URL ist ungueltig');
  });

  it('waits for disabled Load Repo button and continues once the shell enables it', async () => {
    const loadButton = buttonContaining('Load Repo');
    const onLoad = vi.fn(() => {
      appendMarker('repo snapshot ready');
    });

    loadButton.disabled = true;
    loadButton.addEventListener('click', onLoad);

    const { installMobileSetupDrawer } = await loadGuidanceModules();

    installMobileSetupDrawer();
    advanceInstallTimers();

    getDrawerFab().click();

    setDrawerValues('https://github.com/owner/repo', 'secret-value');
    getDrawerSaveButton().click();

    vi.advanceTimersByTime(500);

    expect(onLoad).not.toHaveBeenCalled();
    expect(getDrawerStatus().textContent).toContain('Waiting for repository load button');

    loadButton.disabled = false;

    vi.advanceTimersByTime(4000);

    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(getDrawerStatus().dataset.phase).toBe('loaded');
  });

  it('lets more menu, coach, and setup drawer coexist without duplicate roots', async () => {
    const modules = await loadGuidanceModules();

    installAll(modules);
    advanceInstallTimers();

    expectSingleGuidanceRoots();

    expect(selectByLabel('Automation Mode').value).toBe('manual');
    expect(getCoach().textContent).toContain('Sovereign Bot');
    expect(getDrawerRoot().textContent).toContain('Repo Setup');
  });

  it('keeps guidance stable after shell text changes from repo setup to review-ready', async () => {
    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    expect(getCoach().className).toContain('yellow');

    appendMarker(
      'Generated Files Review SELF REVIEW: ACCEPTED generated-output-accepted generated files review',
    );

    installMobileOperatorCoach();
    advanceInstallTimers();

    const coach = getCoach();

    expect(document.querySelectorAll(`#${COACH_ID}`)).toHaveLength(1);
    expect(coach.className).toContain('yellow');
    expectTextContainsAny(coach.textContent, ['Ergebnis ist bereit', 'Ergebnis bereit', 'Files']);
  });

  it('keeps guidance stable after shell text changes from active work to real stopper', async () => {
    mountShell('<section>package-build running workflow-watch in progress</section>');

    const { installMobileOperatorCoach } = await loadGuidanceModules();

    installMobileOperatorCoach();
    advanceInstallTimers();

    expect(getCoach().className).toContain('yellow');
    expectTextContainsAny(getCoach().textContent, ['Ich arbeite', 'Live Monitor']);

    appendMarker('Workflow failed. Package build failed with exit code 1.');

    installMobileOperatorCoach();
    advanceInstallTimers();

    expect(document.querySelectorAll(`#${COACH_ID}`)).toHaveLength(1);
    expect(getCoach().className).toContain('red');
    expectTextContainsAny(getCoach().textContent, ['Stopper', 'Repair', 'Log']);
  });

  it('survives app shell rebuild and reinstalls all mobile guidance roots cleanly', async () => {
    const modules = await loadGuidanceModules();

    installAll(modules);
    advanceInstallTimers();

    expectSingleGuidanceRoots();

    mountShell(
      '<section>Generated Files Review SELF REVIEW: ACCEPTED generated-output-accepted</section>',
    );

    expect(document.getElementById(MORE_MENU_ID)).toBeNull();
    expect(document.getElementById(COACH_ID)).toBeNull();
    expect(document.getElementById(DRAWER_ID)).toBeNull();

    installAll(modules);
    advanceInstallTimers();

    expectSingleGuidanceRoots();

    expect(selectByLabel('Automation Mode').value).toBe('manual');
    expect(getCoach().className).toContain('yellow');
    expect(getDrawerRoot().textContent).toContain('Repo Setup');
  });

  it('keeps the primary work path visible after all mobile guidance systems are active', async () => {
    const modules = await loadGuidanceModules();

    installAll(modules);
    advanceInstallTimers();

    expectVisibleButton('Repo');
    expectVisibleButton('Builder');
    expectVisibleButton('Files');
    expectVisibleButton('Diff');
    expect(selectByLabel('Automation Mode').value).toBe('manual');
  });
});
