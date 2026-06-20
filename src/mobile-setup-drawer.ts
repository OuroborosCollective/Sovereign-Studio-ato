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
const RENDER_DELAY_MS = 900;
const INPUT_RETRY_LIMIT = 48;
const LOAD_RETRY_LIMIT = 40;
const OUTCOME_RETRY_LIMIT = 180;
const RETRY_DELAY_MS = 120;
const OUTCOME_DELAY_MS = 240;

const REPO_INPUT_SELECTORS = [
  '[data-testid="github-repo-url-input"]',
  '[data-mobile-role="github-repo-url-input"]',
  'input[name="github-repo-url"]',
  'input[name="repoUrl"]',
  'input[id="github-repo-url-input"]',
  'input[aria-label="GitHub Repository URL"]',
  'input[placeholder*="github.com"]',
  'input[type="url"]',
] as const;

const ACCESS_INPUT_SELECTORS = [
  '[data-testid="github-token-input"]',
  '[data-mobile-role="github-token-input"]',
  'input[name="github-token"]',
  'input[name="accessValue"]',
  'input[id="github-token-input"]',
  'input[aria-label="GitHub private access"]',
  'input[placeholder*="GitHub Zugang"]',
  'input[type="password"]',
] as const;

type MobileWindow = Window & typeof globalThis & { [INSTALL_FLAG]?: boolean };
type RepoSetupStage = Parameters<typeof createMobileRepoSetupState>[1];

interface SetupDraft {
  repoUrl: string;
  accessValue: string;
}

interface RepoUrlValidation {
  valid: boolean;
  message?: string;
}

let activeSessionId = 0;

function mobileWindow(): MobileWindow {
  return window as MobileWindow;
}

function normalize(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

function readDraft(): SetupDraft {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { repoUrl: '', accessValue: '' };
    const parsed = JSON.parse(raw) as Partial<SetupDraft>;
    return {
      repoUrl: typeof parsed.repoUrl === 'string' ? normalize(parsed.repoUrl) : '',
      accessValue: '',
    };
  } catch {
    return { repoUrl: '', accessValue: '' };
  }
}

function writeDraft(draft: SetupDraft): void {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ repoUrl: normalize(draft.repoUrl) }),
    );
  } catch {
    // Optional local helper only.
  }
}

function isActiveSession(sessionId: number): boolean {
  return sessionId === activeSessionId;
}

function writeStage(detail: MobileRepoSetupDetail, stage: RepoSetupStage, message: string): void {
  try {
    writeMobileRepoSetupState(createMobileRepoSetupState(detail, stage, message));
  } catch {
    // Side-channel only.
  }
}

function setStatus(message: string, phase = 'idle'): void {
  const status = document.getElementById(DRAWER_ID)?.querySelector<HTMLElement>('[data-role="setup-status"]');
  if (!status) return;
  status.textContent = message;
  status.dataset.phase = phase;
}

function setSessionStatus(sessionId: number, message: string, phase = 'idle'): boolean {
  if (!isActiveSession(sessionId)) return false;

  const status = document.getElementById(DRAWER_ID)?.querySelector<HTMLElement>('[data-role="setup-status"]');
  if (!status) return false;
  if (status.dataset.phase === 'loaded' && phase !== 'loaded') return false;

  status.textContent = message;
  status.dataset.phase = phase;
  return true;
}

function pageText(): string {
  return document.body?.textContent?.toLowerCase() ?? '';
}

function findButton(label: string): HTMLButtonElement | null {
  const wanted = label.toLowerCase();
  return Array.from(document.querySelectorAll('button')).find((button) => {
    if (button.closest(`#${DRAWER_ID}`)) return false;
    return (button.textContent ?? '').trim().toLowerCase() === wanted;
  }) ?? null;
}

function findButtonContaining(label: string): HTMLButtonElement | null {
  const wanted = label.toLowerCase();
  return Array.from(document.querySelectorAll('button')).find((button) => {
    if (button.closest(`#${DRAWER_ID}`)) return false;
    return ((button.textContent ?? '').trim().toLowerCase()).includes(wanted);
  }) ?? null;
}

function findLoadRepoButton(): HTMLButtonElement | null {
  return findButtonContaining('load repo') ?? findButtonContaining('repo laden') ?? findButtonContaining('laden');
}

function setNativeInputValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  if (setter) setter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function queryAppInput(selectors: readonly string[]): HTMLInputElement | null {
  for (const selector of selectors) {
    const input = Array.from(document.querySelectorAll<HTMLInputElement>(selector)).find(
      (candidate) => !candidate.closest(`#${DRAWER_ID}`),
    );
    if (input) return input;
  }
  return null;
}

function visibleTextFor(input: HTMLInputElement): string {
  const labelText = input.closest('label')?.textContent ?? '';
  return `${input.getAttribute('aria-label') ?? ''} ${input.getAttribute('placeholder') ?? ''} ${input.name} ${input.id} ${labelText}`.toLowerCase();
}

function findRepoUrlInput(): HTMLInputElement | null {
  const direct = queryAppInput(REPO_INPUT_SELECTORS);
  if (direct) return direct;

  return Array.from(document.querySelectorAll<HTMLInputElement>('input')).find((input) => {
    if (input.closest(`#${DRAWER_ID}`)) return false;
    const text = visibleTextFor(input);
    return text.includes('repository url') || text.includes('repo url') || text.includes('github.com');
  }) ?? null;
}

function findAccessInput(): HTMLInputElement | null {
  const direct = queryAppInput(ACCESS_INPUT_SELECTORS);
  if (direct) return direct;

  return Array.from(document.querySelectorAll<HTMLInputElement>('input')).find((input) => {
    if (input.closest(`#${DRAWER_ID}`)) return false;
    const text = visibleTextFor(input);
    return text.includes('private access') || text.includes('token') || text.includes('zugang');
  }) ?? null;
}

function validateRepoUrl(url: string): RepoUrlValidation {
  const trimmed = url.trim();
  if (!trimmed) return { valid: false, message: 'GitHub Repository URL fehlt.' };

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return { valid: false, message: 'GitHub Repository URL muss http oder https nutzen.' };
    }
    return { valid: true };
  } catch {
    return { valid: false, message: 'GitHub Repository URL ist ungueltig.' };
  }
}

function watchRepoLoadOutcome(detail: MobileRepoSetupDetail, sessionId: number, attempt = 0): void {
  if (!isActiveSession(sessionId)) return;

  const text = pageText();
  if (
    text.includes('echte repo-einträge geladen') ||
    text.includes('repo geladen') ||
    text.includes('repo snapshot ready') ||
    text.includes('repository loaded') ||
    text.includes('repo loaded')
  ) {
    if (setSessionStatus(sessionId, 'Repository load completed.', 'loaded')) {
      writeStage(detail, 'loaded', 'Repository load completed.');
    }
    return;
  }

  if (text.includes('ungültige github url') || text.includes('repo-info fehler') || text.includes('repository nicht gefunden')) {
    if (setSessionStatus(sessionId, 'Repository load failed.', 'failed')) {
      writeStage(detail, 'failed', 'Repository load failed.');
    }
    return;
  }

  if (attempt >= OUTCOME_RETRY_LIMIT) {
    if (setSessionStatus(sessionId, 'Repository load outcome was not detected.', 'failed')) {
      writeStage(detail, 'failed', 'Repository load outcome was not detected.');
    }
    return;
  }

  window.setTimeout(() => watchRepoLoadOutcome(detail, sessionId, attempt + 1), OUTCOME_DELAY_MS);
}

function clickLoadRepoWhenReady(detail: MobileRepoSetupDetail, sessionId: number, attempt = 0): void {
  if (!isActiveSession(sessionId)) return;

  const button = findLoadRepoButton();
  if (button && !button.disabled) {
    if (!setSessionStatus(sessionId, 'Repository load button clicked.', 'loading')) return;
    writeStage(detail, 'loading', 'Repository load button clicked.');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    watchRepoLoadOutcome(detail, sessionId);
    return;
  }

  if (attempt >= LOAD_RETRY_LIMIT) {
    if (setSessionStatus(sessionId, 'Repository load button was not found or remained disabled.', 'failed')) {
      writeStage(detail, 'failed', 'Repository load button was not found or remained disabled.');
    }
    return;
  }

  setSessionStatus(sessionId, 'Waiting for repository load button.', 'applied');
  window.setTimeout(() => clickLoadRepoWhenReady(detail, sessionId, attempt + 1), RETRY_DELAY_MS);
}

function applyDraftToRepoTab(draft: SetupDraft, detail: MobileRepoSetupDetail, sessionId: number, attempt = 0): void {
  if (!isActiveSession(sessionId)) return;
  if (attempt === 0) findButton('Repo')?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

  window.setTimeout(() => {
    if (!isActiveSession(sessionId)) return;

    const repo = findRepoUrlInput();
    const access = findAccessInput();

    if (!repo && attempt < INPUT_RETRY_LIMIT) {
      setSessionStatus(sessionId, 'Waiting for Repo tab inputs.', 'submitted');
      applyDraftToRepoTab(draft, detail, sessionId, attempt + 1);
      return;
    }

    if (!repo) {
      if (setSessionStatus(sessionId, 'Repo URL input was not found.', 'failed')) {
        writeStage(detail, 'failed', 'Repo URL input was not found.');
      }
      return;
    }

    if (draft.repoUrl) setNativeInputValue(repo, draft.repoUrl);
    if (access && draft.accessValue) setNativeInputValue(access, draft.accessValue);
    repo.focus();

    if (setSessionStatus(sessionId, 'Repo setup values applied to Repo tab.', 'applied')) {
      writeStage(detail, 'applied', 'Repo setup values applied to Repo tab.');
    }
    clickLoadRepoWhenReady(detail, sessionId);
  }, attempt === 0 ? 160 : RETRY_DELAY_MS);
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${DRAWER_ID} .setup-fab { position: fixed; top: calc(env(safe-area-inset-top, 0px) + .7rem); right: .75rem; z-index: 50; min-width: 2.75rem; min-height: 2.75rem; border-radius: 999px; border: 1px solid rgba(34,211,238,.45); background: rgba(2,6,23,.92); color: #e0f2fe; font-weight: 950; }
    #${DRAWER_ID} .setup-panel { position: fixed; inset: auto .75rem calc(env(safe-area-inset-bottom, 0px) + .75rem) .75rem; z-index: 55; border: 1px solid rgba(34,211,238,.38); border-radius: 1.15rem; background: linear-gradient(135deg, rgba(2,6,23,.97), rgba(15,23,42,.92)); color: #e2e8f0; box-shadow: 0 .9rem 2rem rgba(0,0,0,.32); padding: .9rem; display: grid; gap: .7rem; max-width: 32rem; }
    #${DRAWER_ID} .setup-panel.hidden { display: none; }
    #${DRAWER_ID} label { display: grid; gap: .3rem; color: #cbd5e1; font-size: .78rem; font-weight: 800; }
    #${DRAWER_ID} input { border: 1px solid rgba(148,163,184,.32); border-radius: .75rem; background: rgba(15,23,42,.9); color: #f8fafc; padding: .62rem .7rem; min-height: 2.45rem; font-size: .84rem; }
    #${DRAWER_ID} .setup-save { border: 1px solid rgba(34,211,238,.42); border-radius: .82rem; background: rgba(8,47,73,.9); color: #e0f2fe; padding: .62rem .7rem; font-weight: 950; }
    #${DRAWER_ID} [data-role="setup-status"] { color: #a5b4fc; font-size: .75rem; font-weight: 850; min-height: 1rem; }
    #${DRAWER_ID} [data-role="setup-status"][data-phase="failed"] { color: #fb7185; }
    #${DRAWER_ID} [data-role="setup-status"][data-phase="loaded"] { color: #34d399; }
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
    input.autocomplete = 'on';
  }
  label.appendChild(input);
  return label;
}

function renderDrawer(): void {
  installStyle();
  if (document.getElementById(DRAWER_ID)) return;

  const draft = readDraft();
  const root = document.createElement('section');
  root.id = DRAWER_ID;

  const fab = document.createElement('button');
  fab.type = 'button';
  fab.className = 'setup-fab';
  fab.textContent = '⚙';
  fab.setAttribute('aria-label', 'Repo Setup öffnen');

  const panel = document.createElement('div');
  panel.className = 'setup-panel hidden';

  const title = document.createElement('strong');
  title.textContent = 'GitHub Repo Setup';

  const saveButton = document.createElement('button');
  saveButton.type = 'button';
  saveButton.className = 'setup-save';
  saveButton.dataset.action = 'save';
  saveButton.textContent = 'Speichern & Repo';

  const status = document.createElement('div');
  status.dataset.role = 'setup-status';
  status.dataset.phase = 'idle';
  status.textContent = 'Bereit.';

  panel.append(
    title,
    createInput('GitHub Repository URL', 'repoUrl', draft.repoUrl),
    createInput('GitHub private access', 'accessValue', draft.accessValue),
    saveButton,
    status,
  );

  fab.addEventListener('click', () => panel.classList.toggle('hidden'));
  saveButton.addEventListener('click', () => {
    const repo = panel.querySelector<HTMLInputElement>('[data-field="repoUrl"]');
    const access = panel.querySelector<HTMLInputElement>('[data-field="accessValue"]');
    const repoUrl = normalize(repo?.value ?? '');
    const accessValue = access?.value.trim() ?? '';
    const validation = validateRepoUrl(repoUrl);

    if (!validation.valid) {
      setStatus(validation.message ?? 'GitHub Repository URL ist ungueltig.', 'failed');
      return;
    }

    const next = { repoUrl, accessValue };
    const detail = createMobileRepoSetupDetail({ ...next, autoLoad: true });
    const sessionId = activeSessionId + 1;
    activeSessionId = sessionId;

    writeDraft(next);
    setSessionStatus(sessionId, 'Repo setup submitted.', 'submitted');
    writeStage(detail, 'dispatched', 'Repo setup submitted.');
    try { dispatchMobileRepoSetup(detail); } catch { /* side-channel only */ }
    applyDraftToRepoTab(next, detail, sessionId);
  });

  root.append(fab, panel);
  document.body.appendChild(root);
}

export function installMobileSetupDrawer(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const win = mobileWindow();
  if (!win[INSTALL_FLAG]) win[INSTALL_FLAG] = true;
  window.setTimeout(renderDrawer, RENDER_DELAY_MS);
}
