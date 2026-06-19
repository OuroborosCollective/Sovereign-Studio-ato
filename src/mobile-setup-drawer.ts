import {
  createMobileRepoSetupDetail,
  createMobileRepoSetupState,
  dispatchMobileRepoSetup,
  writeMobileRepoSetupState,
  type MobileRepoSetupDetail,
} from './mobile-setup-bridge';

const DRAWER_ID = 'sovereign-mobile-setup-drawer';
const STYLE_ID = 'sovereign-mobile-setup-style';
const STORAGE_KEY = 'sovereign-mobile-setup-draft';
const INSTALL_FLAG = '__sovereignMobileSetupDrawerInstalled';

const MAX_REPO_LOAD_ATTEMPTS = 22;
const MAX_LOAD_BUTTON_ATTEMPTS = 14;
const MAX_APPLY_ATTEMPTS = 14;
const RENDER_DELAY_MS = 900;

type MobileWindow = Window &
  typeof globalThis & {
    [INSTALL_FLAG]?: boolean;
  };

interface SetupDraft {
  repoUrl: string;
}

interface SetupSubmission {
  repoUrl: string;
  accessValue: string;
}

type RepoSetupStage = Parameters<typeof createMobileRepoSetupState>[1];

type SessionPhase =
  | 'idle'
  | 'submitted'
  | 'repo-tab'
  | 'applied'
  | 'loading'
  | 'loaded'
  | 'failed';

interface SetupSession {
  id: number;
  detail: MobileRepoSetupDetail;
  submission: SetupSubmission;
  phase: SessionPhase;
  message: string;
  timers: Set<number>;
}

const EMPTY_DRAFT: SetupDraft = {
  repoUrl: '',
};

const SUCCESS_TEXT_MARKERS = [
  'echte repo-einträge geladen',
  'echte repo-eintraege geladen',
  'repo geladen',
  'repository loaded',
  'repo snapshot ready',
  'snapshot ready',
  'repository load completed',
];

const FAILURE_TEXT_MARKERS = [
  'ungültige github url',
  'ungueltige github url',
  'repo-info fehler',
  'repository nicht gefunden',
  'repository not found',
  'repo load failed',
  'repository load failed',
  'bad credentials',
  'invalid credentials',
  '401',
  '403',
  '404',
];

let sessionSequence = 0;
let activeSession: SetupSession | null = null;

function mobileWindow(): MobileWindow {
  return window as MobileWindow;
}

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

function normalizeRepoUrl(value: string): string {
  return normalizeText(value);
}

function normalizeAccessValue(value: string): string {
  return value.trim();
}

function safeReadStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeWriteStorage(key: string, value: string): boolean {
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function readDraft(): SetupDraft {
  const raw = safeReadStorage(STORAGE_KEY);
  if (!raw) return EMPTY_DRAFT;

  try {
    const parsed = JSON.parse(raw) as Partial<SetupDraft>;

    return {
      repoUrl: typeof parsed.repoUrl === 'string' ? normalizeRepoUrl(parsed.repoUrl) : '',
    };
  } catch {
    return EMPTY_DRAFT;
  }
}

function writeDraft(draft: SetupDraft): boolean {
  return safeWriteStorage(
    STORAGE_KEY,
    JSON.stringify({
      repoUrl: normalizeRepoUrl(draft.repoUrl),
    }),
  );
}

function writeStage(
  detail: MobileRepoSetupDetail,
  stage: RepoSetupStage,
  message: string,
): void {
  try {
    writeMobileRepoSetupState(createMobileRepoSetupState(detail, stage, message));
  } catch {
    // Side-channel only. Never break the drawer flow.
  }
}

function pageText(): string {
  return document.body?.textContent?.toLowerCase() ?? '';
}

function hasAnyMarker(source: string, markers: string[]): boolean {
  return markers.some((marker) => source.includes(marker));
}

function isActiveSession(session: SetupSession): boolean {
  return activeSession?.id === session.id;
}

function clearSessionTimers(session: SetupSession): void {
  for (const timer of session.timers) {
    window.clearTimeout(timer);
  }

  session.timers.clear();
}

function scheduleSession(
  session: SetupSession,
  callback: () => void,
  delayMs: number,
): void {
  const timer = window.setTimeout(() => {
    session.timers.delete(timer);

    if (!isActiveSession(session)) return;

    callback();
  }, delayMs);

  session.timers.add(timer);
}

function setDrawerStatus(message: string, phase: SessionPhase = 'idle'): void {
  const root = document.getElementById(DRAWER_ID);
  const status = root?.querySelector<HTMLElement>('[data-role="setup-status"]');

  if (!status) return;

  status.textContent = message;
  status.dataset.phase = phase;
}

function setSessionPhase(
  session: SetupSession,
  phase: SessionPhase,
  message: string,
  stage?: RepoSetupStage,
): void {
  if (!isActiveSession(session)) return;

  session.phase = phase;
  session.message = message;

  setDrawerStatus(message, phase);

  if (stage) {
    writeStage(session.detail, stage, message);
  }
}

function failSession(session: SetupSession, message: string): void {
  if (!isActiveSession(session)) return;

  clearSessionTimers(session);
  setSessionPhase(session, 'failed', message, 'failed');
}

function completeSession(session: SetupSession, message: string): void {
  if (!isActiveSession(session)) return;

  clearSessionTimers(session);
  setSessionPhase(session, 'loaded', message, 'loaded');
}

function buttonText(button: HTMLButtonElement): string {
  return (button.textContent ?? '').trim().toLowerCase();
}

function findButton(label: string): HTMLButtonElement | null {
  const needle = label.toLowerCase();

  return (
    Array.from(document.querySelectorAll('button')).find(
      (button) => buttonText(button) === needle,
    ) ?? null
  );
}

function findButtonContaining(label: string): HTMLButtonElement | null {
  const needle = label.toLowerCase();

  return (
    Array.from(document.querySelectorAll('button')).find((button) =>
      buttonText(button).includes(needle),
    ) ?? null
  );
}

function setNativeInputValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  )?.set;

  if (setter) {
    setter.call(input, value);
  } else {
    input.value = value;
  }

  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function inputByLabel(label: string): HTMLInputElement | null {
  const exact = document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);
  if (exact) return exact;

  const needle = label.toLowerCase();

  return (
    Array.from(document.querySelectorAll<HTMLInputElement>('input')).find((input) => {
      const aria = input.getAttribute('aria-label')?.toLowerCase() ?? '';
      const placeholder = input.getAttribute('placeholder')?.toLowerCase() ?? '';
      const name = input.getAttribute('name')?.toLowerCase() ?? '';
      const dataField = input.getAttribute('data-field')?.toLowerCase() ?? '';

      return (
        aria.includes(needle) ||
        placeholder.includes(needle) ||
        name.includes(needle) ||
        dataField.includes(needle)
      );
    }) ?? null
  );
}

function findRepoInput(): HTMLInputElement | null {
  return (
    inputByLabel('GitHub Repository URL') ??
    inputByLabel('Repository URL') ??
    inputByLabel('repoUrl') ??
    null
  );
}

function findAccessInput(): HTMLInputElement | null {
  return (
    inputByLabel('GitHub private access') ??
    inputByLabel('private access') ??
    inputByLabel('accessValue') ??
    inputByLabel('token') ??
    null
  );
}

function watchRepoLoadOutcome(session: SetupSession, attempt = 0): void {
  if (!isActiveSession(session)) return;

  const text = pageText();

  if (hasAnyMarker(text, SUCCESS_TEXT_MARKERS)) {
    completeSession(session, 'Repository load completed.');
    return;
  }

  if (hasAnyMarker(text, FAILURE_TEXT_MARKERS)) {
    failSession(session, 'Repository load failed.');
    return;
  }

  if (attempt < MAX_REPO_LOAD_ATTEMPTS) {
    scheduleSession(session, () => watchRepoLoadOutcome(session, attempt + 1), 260 + attempt * 120);
    return;
  }

  failSession(session, 'Repository load outcome was not detected.');
}

function clickLoadRepoWhenReady(session: SetupSession, attempt = 0): void {
  if (!isActiveSession(session)) return;

  const button =
    findButtonContaining('load repo') ??
    findButtonContaining('repo laden') ??
    findButtonContaining('repository laden') ??
    findButtonContaining('laden');

  if (button && !button.disabled) {
    setSessionPhase(session, 'loading', 'Repository load button clicked.', 'loading');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    watchRepoLoadOutcome(session);
    return;
  }

  if (attempt < MAX_LOAD_BUTTON_ATTEMPTS) {
    setSessionPhase(session, 'repo-tab', 'Waiting for repository load button.');
    scheduleSession(session, () => clickLoadRepoWhenReady(session, attempt + 1), 140 + attempt * 120);
    return;
  }

  failSession(session, 'Repository load button was not found or remained disabled.');
}

function openRepoTab(session: SetupSession): void {
  if (!isActiveSession(session)) return;

  const repoButton = findButton('Repo') ?? findButtonContaining('Repo');

  if (repoButton) {
    setSessionPhase(session, 'repo-tab', 'Repo tab selected.');
    repoButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  } else {
    setSessionPhase(session, 'repo-tab', 'Repo tab button not found yet.');
  }
}

function applyDraftToRepoTab(session: SetupSession, attempt = 0): void {
  if (!isActiveSession(session)) return;

  if (attempt === 0) {
    openRepoTab(session);
  }

  scheduleSession(session, () => {
    if (!isActiveSession(session)) return;

    const repo = findRepoInput();
    const access = findAccessInput();

    if (!repo && attempt < MAX_APPLY_ATTEMPTS) {
      setSessionPhase(session, 'repo-tab', 'Waiting for Repo tab inputs.');
      scheduleSession(session, () => applyDraftToRepoTab(session, attempt + 1), 160 + attempt * 120);
      return;
    }

    if (!repo) {
      failSession(session, 'Repo URL input was not found.');
      return;
    }

    if (session.submission.repoUrl) {
      setNativeInputValue(repo, session.submission.repoUrl);
    }

    if (access && session.submission.accessValue) {
      setNativeInputValue(access, session.submission.accessValue);
    }

    repo.focus();

    setSessionPhase(session, 'applied', 'Repo setup values applied to Repo tab.', 'applied');
    clickLoadRepoWhenReady(session);
  }, attempt === 0 ? 160 : 0);
}

function validateSubmission(submission: SetupSubmission): string | null {
  if (!submission.repoUrl) {
    return 'GitHub Repository URL fehlt.';
  }

  try {
    const url = new URL(submission.repoUrl);

    if (!['http:', 'https:'].includes(url.protocol)) {
      return 'GitHub Repository URL muss http oder https nutzen.';
    }
  } catch {
    return 'GitHub Repository URL ist ungueltig.';
  }

  return null;
}

function createSession(submission: SetupSubmission): SetupSession {
  if (activeSession) {
    clearSessionTimers(activeSession);
  }

  const detail = createMobileRepoSetupDetail({
    ...submission,
    autoLoad: true,
  });

  const session: SetupSession = {
    id: ++sessionSequence,
    detail,
    submission,
    phase: 'submitted',
    message: 'Repo setup submitted.',
    timers: new Set<number>(),
  };

  activeSession = session;
  return session;
}

function startRepoSetup(submission: SetupSubmission): void {
  const validationError = validateSubmission(submission);

  if (validationError) {
    setDrawerStatus(validationError, 'failed');
    return;
  }

  const session = createSession(submission);

  writeDraft({
    repoUrl: submission.repoUrl,
  });

  setSessionPhase(session, 'submitted', 'Repo setup submitted.', 'applied');

  try {
    dispatchMobileRepoSetup(session.detail);
  } catch {
    setDrawerStatus('Repo setup event dispatch failed, applying values directly.', 'submitted');
  }

  applyDraftToRepoTab(session);
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${DRAWER_ID} .setup-fab {
      position: fixed;
      top: calc(env(safe-area-inset-top, 0px) + .7rem);
      right: .75rem;
      z-index: 50;
      min-width: 2.75rem;
      min-height: 2.75rem;
      border-radius: 999px;
      border: 1px solid rgba(34,211,238,.45);
      background: rgba(2,6,23,.92);
      color: #e0f2fe;
      box-shadow: 0 .6rem 1.5rem rgba(0,0,0,.32), 0 0 1rem rgba(34,211,238,.16);
      font-weight: 950;
    }

    #${DRAWER_ID} .setup-panel {
      position: fixed;
      inset: auto .75rem calc(env(safe-area-inset-bottom, 0px) + .75rem) .75rem;
      z-index: 55;
      border: 1px solid rgba(34,211,238,.38);
      border-radius: 1.15rem;
      background: linear-gradient(135deg, rgba(2,6,23,.97), rgba(15,23,42,.92));
      color: #e2e8f0;
      box-shadow: 0 .9rem 2rem rgba(0,0,0,.32);
      padding: .9rem;
      display: grid;
      gap: .7rem;
      max-width: 32rem;
    }

    #${DRAWER_ID} .setup-panel.hidden {
      display: none;
    }

    #${DRAWER_ID} label {
      display: grid;
      gap: .3rem;
      color: #cbd5e1;
      font-size: .78rem;
      font-weight: 800;
    }

    #${DRAWER_ID} input {
      border: 1px solid rgba(148,163,184,.32);
      border-radius: .75rem;
      background: rgba(15,23,42,.9);
      color: #f8fafc;
      padding: .62rem .7rem;
      min-height: 2.45rem;
      font-size: .84rem;
    }

    #${DRAWER_ID} .setup-actions {
      display: grid;
      grid-template-columns: 1fr;
      gap: .5rem;
    }

    #${DRAWER_ID} .setup-save {
      border: 1px solid rgba(34,211,238,.42);
      border-radius: .82rem;
      background: rgba(8,47,73,.9);
      color: #e0f2fe;
      padding: .62rem .7rem;
      font-weight: 950;
    }

    #${DRAWER_ID} [data-role="setup-status"] {
      color: #a5b4fc;
      font-size: .75rem;
      font-weight: 850;
      min-height: 1rem;
    }

    #${DRAWER_ID} [data-role="setup-status"][data-phase="failed"] {
      color: #fb7185;
    }

    #${DRAWER_ID} [data-role="setup-status"][data-phase="loaded"] {
      color: #34d399;
    }
  `;

  document.head.appendChild(style);
}

function createInput(labelText: string, field: 'repoUrl' | 'accessValue', value = ''): HTMLLabelElement {
  const label = document.createElement('label');
  label.textContent = labelText;

  const input = document.createElement('input');
  input.dataset.field = field;
  input.name = field;
  input.value = value;
  input.setAttribute('aria-label', labelText);

  if (field === 'accessValue') {
    input.type = 'password';
    input.autocomplete = 'off';
  } else {
    input.type = 'url';
    input.autocomplete = 'url';
  }

  label.appendChild(input);
  return label;
}

function renderDrawer(): void {
  if (typeof document === 'undefined') return;

  installStyle();

  let root = document.getElementById(DRAWER_ID);
  if (root) return;

  const draft = readDraft();

  root = document.createElement('section');
  root.id = DRAWER_ID;
  root.setAttribute('aria-label', 'Sovereign mobile setup drawer');

  const fab = document.createElement('button');
  fab.type = 'button';
  fab.className = 'setup-fab';
  fab.textContent = '⚙';
  fab.setAttribute('aria-label', 'Repo Setup öffnen');

  const panel = document.createElement('div');
  panel.className = 'setup-panel hidden';

  const title = document.createElement('strong');
  title.textContent = 'GitHub Repo Setup';

  const repoInput = createInput('GitHub Repository URL', 'repoUrl', draft.repoUrl);
  const accessInput = createInput('GitHub private access', 'accessValue', '');

  const status = document.createElement('div');
  status.dataset.role = 'setup-status';
  status.dataset.phase = 'idle';
  status.textContent = 'Bereit.';

  const actions = document.createElement('div');
  actions.className = 'setup-actions';

  const saveButton = document.createElement('button');
  saveButton.type = 'button';
  saveButton.className = 'setup-save';
  saveButton.textContent = 'Speichern & Repo';
  saveButton.addEventListener('click', () => {
    const repo = panel.querySelector<HTMLInputElement>('[data-field="repoUrl"]');
    const access = panel.querySelector<HTMLInputElement>('[data-field="accessValue"]');

    startRepoSetup({
      repoUrl: normalizeRepoUrl(repo?.value ?? ''),
      accessValue: normalizeAccessValue(access?.value ?? ''),
    });
  });

  actions.appendChild(saveButton);
  panel.append(title, repoInput, accessInput, actions, status);

  fab.addEventListener('click', () => {
    panel.classList.toggle('hidden');
  });

  root.append(fab, panel);
  document.body.appendChild(root);
}

export function installMobileSetupDrawer(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const win = mobileWindow();
  if (!win[INSTALL_FLAG]) {
    win[INSTALL_FLAG] = true;
  }

  window.setTimeout(renderDrawer, RENDER_DELAY_MS);
}
