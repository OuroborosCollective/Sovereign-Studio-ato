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

type MobileWindow = Window & typeof globalThis & { [INSTALL_FLAG]?: boolean };
type RepoSetupStage = Parameters<typeof createMobileRepoSetupState>[1];

interface SetupDraft {
  repoUrl: string;
  accessValue: string;
}

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
      accessValue: typeof parsed.accessValue === 'string' ? parsed.accessValue.trim() : '',
    };
  } catch {
    return { repoUrl: '', accessValue: '' };
  }
}

function writeDraft(draft: SetupDraft): void {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ repoUrl: normalize(draft.repoUrl), accessValue: draft.accessValue.trim() }),
    );
  } catch {
    // Optional local helper only.
  }
}

function writeStage(detail: MobileRepoSetupDetail, stage: RepoSetupStage, message: string): void {
  try {
    writeMobileRepoSetupState(createMobileRepoSetupState(detail, stage, message));
  } catch {
    // Side-channel only.
  }
}

function pageText(): string {
  return document.body?.textContent?.toLowerCase() ?? '';
}

function findButton(label: string): HTMLButtonElement | null {
  const wanted = label.toLowerCase();
  return Array.from(document.querySelectorAll('button')).find((button) =>
    (button.textContent ?? '').trim().toLowerCase() === wanted,
  ) ?? null;
}

function findButtonContaining(label: string): HTMLButtonElement | null {
  const wanted = label.toLowerCase();
  return Array.from(document.querySelectorAll('button')).find((button) =>
    ((button.textContent ?? '').trim().toLowerCase()).includes(wanted),
  ) ?? null;
}

function setNativeInputValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  if (setter) setter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function inputByLabel(label: string): HTMLInputElement | null {
  return document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);
}

function setStatus(message: string, phase = 'idle'): void {
  const status = document.getElementById(DRAWER_ID)?.querySelector<HTMLElement>('[data-role="setup-status"]');
  if (!status) return;
  status.textContent = message;
  status.dataset.phase = phase;
}

function watchRepoLoadOutcome(detail: MobileRepoSetupDetail, attempt = 0): void {
  const text = pageText();
  if (text.includes('echte repo-einträge geladen') || text.includes('repo geladen') || text.includes('repo snapshot ready')) {
    setStatus('Repository load completed.', 'loaded');
    writeStage(detail, 'loaded', 'Repository load completed.');
    return;
  }
  if (text.includes('ungültige github url') || text.includes('repo-info fehler') || text.includes('repository nicht gefunden')) {
    setStatus('Repository load failed.', 'failed');
    writeStage(detail, 'failed', 'Repository load failed.');
    return;
  }
  if (attempt < 22) window.setTimeout(() => watchRepoLoadOutcome(detail, attempt + 1), 260 + attempt * 120);
}

function clickLoadRepoWhenReady(detail: MobileRepoSetupDetail, attempt = 0): void {
  const button = findButtonContaining('load repo') ?? findButtonContaining('repo laden') ?? findButtonContaining('laden');
  if (button && !button.disabled) {
    setStatus('Repository load button clicked.', 'loading');
    writeStage(detail, 'loading', 'Repository load button clicked.');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    watchRepoLoadOutcome(detail);
    return;
  }
  if (attempt < 14) window.setTimeout(() => clickLoadRepoWhenReady(detail, attempt + 1), 140 + attempt * 120);
}

function applyDraftToRepoTab(draft: SetupDraft, detail: MobileRepoSetupDetail, attempt = 0): void {
  if (attempt === 0) findButton('Repo')?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

  window.setTimeout(() => {
    const repo = inputByLabel('GitHub Repository URL');
    const access = inputByLabel('GitHub private access');

    if (!repo && attempt < 14) {
      applyDraftToRepoTab(draft, detail, attempt + 1);
      return;
    }

    if (!repo) {
      setStatus('Repo URL input was not found.', 'failed');
      writeStage(detail, 'failed', 'Repo URL input was not found.');
      return;
    }

    if (draft.repoUrl) setNativeInputValue(repo, draft.repoUrl);
    if (access && draft.accessValue) setNativeInputValue(access, draft.accessValue);
    repo.focus();
    setStatus('Repo setup values applied to Repo tab.', 'applied');
    writeStage(detail, 'applied', 'Repo setup values applied to Repo tab.');
    clickLoadRepoWhenReady(detail);
  }, attempt === 0 ? 160 : 120);
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
    const next = { repoUrl: normalize(repo?.value ?? ''), accessValue: access?.value.trim() ?? '' };
    const detail = createMobileRepoSetupDetail({ ...next, autoLoad: true });
    writeDraft(next);
    setStatus('Repo setup submitted.', 'submitted');
    writeStage(detail, 'applied', 'Repo setup submitted.');
    try { dispatchMobileRepoSetup(detail); } catch { /* side-channel only */ }
    applyDraftToRepoTab(next, detail);
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
