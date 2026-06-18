const DRAWER_ID = 'sovereign-mobile-setup-drawer';
const STYLE_ID = 'sovereign-mobile-setup-style';
const STORAGE_KEY = 'sovereign-mobile-setup-draft';

interface SetupDraft {
  repoUrl: string;
  accessValue: string;
}

function readDraft(): SetupDraft {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { repoUrl: '', accessValue: '' };
    const parsed = JSON.parse(raw) as Partial<SetupDraft>;
    return {
      repoUrl: typeof parsed.repoUrl === 'string' ? parsed.repoUrl : '',
      accessValue: typeof parsed.accessValue === 'string' ? parsed.accessValue : '',
    };
  } catch {
    return { repoUrl: '', accessValue: '' };
  }
}

function writeDraft(draft: SetupDraft): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
}

function findButton(label: string): HTMLButtonElement | null {
  return Array.from(document.querySelectorAll('button')).find((button) => (button.textContent ?? '').trim().toLowerCase() === label.toLowerCase()) ?? null;
}

function setNativeInputValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function inputByLabel(label: string): HTMLInputElement | null {
  return document.querySelector(`input[aria-label="${label}"]`);
}

function applyDraftToRepoTab(draft: SetupDraft): void {
  findButton('Repo')?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  window.setTimeout(() => {
    const repo = inputByLabel('GitHub Repository URL');
    const access = inputByLabel('GitHub private access');
    if (repo && draft.repoUrl) setNativeInputValue(repo, draft.repoUrl);
    if (access && draft.accessValue) setNativeInputValue(access, draft.accessValue);
    repo?.focus();
  }, 120);
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${DRAWER_ID} .setup-fab { position: fixed; top: calc(env(safe-area-inset-top, 0px) + .7rem); right: .75rem; z-index: 50; min-width: 2.75rem; min-height: 2.75rem; border-radius: 999px; border: 1px solid rgba(34,211,238,.45); background: rgba(2,6,23,.92); color: #e0f2fe; box-shadow: 0 .6rem 1.5rem rgba(0,0,0,.32), 0 0 1rem rgba(34,211,238,.16); font-weight: 950; }
    #${DRAWER_ID} .setup-panel { position: fixed; inset: auto .75rem calc(env(safe-area-inset-bottom, 0px) + .75rem) .75rem; z-index: 55; border: 1px solid rgba(34,211,238,.38); border-radius: 1.15rem; background: linear-gradient(135deg, rgba(2,6,23,.98), rgba(15,23,42,.96)); color: #e2e8f0; padding: .9rem; box-shadow: 0 1rem 2.4rem rgba(0,0,0,.46); }
    #${DRAWER_ID} .hidden { display: none; }
    #${DRAWER_ID} label { display: block; margin-top: .7rem; font-size: .72rem; font-weight: 900; text-transform: uppercase; letter-spacing: .05em; color: #bae6fd; }
    #${DRAWER_ID} input { margin-top: .35rem; width: 100%; min-height: 2.65rem; border-radius: .85rem; border: 1px solid rgba(148,163,184,.28); background: rgba(15,23,42,.92); color: #f8fafc; padding: .58rem .7rem; font-size: .9rem; }
    #${DRAWER_ID} .actions { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: .8rem; }
    #${DRAWER_ID} button { cursor: pointer; }
    #${DRAWER_ID} .primary { border: 1px solid rgba(34,211,238,.45); background: rgba(8,47,73,.8); color: #e0f2fe; border-radius: .85rem; padding: .65rem .75rem; font-weight: 950; }
    #${DRAWER_ID} .ghost { border: 1px solid rgba(148,163,184,.25); background: rgba(15,23,42,.76); color: #cbd5e1; border-radius: .85rem; padding: .65rem .75rem; font-weight: 850; }
    #${DRAWER_ID} .hint { margin-top: .6rem; color: #fef3c7; font-size: .72rem; line-height: 1.35; }
  `;
  document.head.appendChild(style);
}

function render(): void {
  installStyle();
  let root = document.getElementById(DRAWER_ID);
  if (!root) {
    root = document.createElement('div');
    root.id = DRAWER_ID;
    document.body.appendChild(root);
  }
  const draft = readDraft();
  root.innerHTML = `
    <button class="setup-fab" type="button" aria-label="Repo Setup oeffnen">⚙</button>
    <section class="setup-panel hidden" role="dialog" aria-label="Repo Setup">
      <strong>Repo Setup</strong>
      <p class="hint">Immer erreichbar: Repo URL und privater GitHub Zugang. Danach springe ich direkt zum Repo-Laden.</p>
      <label>GitHub Repository URL<input data-field="repoUrl" value="${draft.repoUrl.replace(/"/g, '&quot;')}" placeholder="https://github.com/owner/repository" /></label>
      <label>GitHub Zugang fuer private Repos / Draft PR<input data-field="accessValue" value="${draft.accessValue.replace(/"/g, '&quot;')}" placeholder="Privaten Zugang einfuegen" type="password" /></label>
      <p class="hint">Zugang nur fuer private Repos oder Draft PRs. Die App zeigt ihn nicht im Log an.</p>
      <div class="actions"><button class="primary" data-action="save" type="button">Speichern & Repo</button><button class="ghost" data-action="close" type="button">Schliessen</button></div>
    </section>
  `;
  const panel = root.querySelector('.setup-panel') as HTMLElement | null;
  root.querySelector('.setup-fab')?.addEventListener('click', () => panel?.classList.toggle('hidden'));
  root.querySelector('[data-action="close"]')?.addEventListener('click', () => panel?.classList.add('hidden'));
  root.querySelector('[data-action="save"]')?.addEventListener('click', () => {
    const next = {
      repoUrl: (root.querySelector('[data-field="repoUrl"]') as HTMLInputElement | null)?.value.trim() ?? '',
      accessValue: (root.querySelector('[data-field="accessValue"]') as HTMLInputElement | null)?.value.trim() ?? '',
    };
    writeDraft(next);
    panel?.classList.add('hidden');
    applyDraftToRepoTab(next);
  });
}

export function installMobileSetupDrawer(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  window.setTimeout(render, 900);
}
