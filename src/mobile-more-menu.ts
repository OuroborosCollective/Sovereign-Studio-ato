const MENU_ID = 'sovereign-more-menu';
const MOBILE_QUERY = '(max-width: 767px)';
const AUTO_MODE_VALUE = 'full-auto-draft-pr';

const PRIMARY_LABELS = ['Repo', 'Chat', 'Builder', 'Files', 'Diff'] as const;

const OPTIONS = [
  'Workflow',
  'Repair',
  'Remote Memory',
  'Pattern Memory',
  'Telemetry',
  'Live Monitor',
  'Readiness',
  'Integrity',
  'Findings',
  'Health',
  'Runtime',
  'Coverage',
] as const;

const PRIMARY = new Set<string>(PRIMARY_LABELS);
const OVERFLOW = new Set<string>(OPTIONS);

type MoreMenuWindow = Window &
  typeof globalThis & {
    __sovereignMoreMenuInstalled?: boolean;
    __sovereignMoreMenuObserver?: MutationObserver;
    __sovereignMoreMenuMedia?: MediaQueryList;
    __sovereignMoreMenuRaf?: number;
    __sovereignMoreMenuTimer?: number;
    __sovereignMoreMenuFallbackInterval?: number;
    __sovereignMoreMenuFallbackRuns?: number;
  };

function runtimeWindow(): MoreMenuWindow {
  return window as MoreMenuWindow;
}

function normalizeLabel(value: string | null | undefined): string {
  return (value ?? '').replace(/\s+/g, ' ').trim();
}

function readButtonLabel(button: HTMLButtonElement): string {
  return normalizeLabel(button.textContent || button.getAttribute('aria-label') || button.title);
}

function isMobileViewport(): boolean {
  if (typeof window === 'undefined') return false;

  const docWidth = document.documentElement?.clientWidth ?? 0;
  if (docWidth <= 0) return true;

  if (typeof window.matchMedia === 'function' && window.matchMedia(MOBILE_QUERY).matches) return true;

  return window.innerWidth < 768;
}

function getAppRoot(): HTMLElement {
  return document.getElementById('root') ?? document.body;
}

function isInsideMoreMenu(element: Element): boolean {
  return Boolean(element.closest(`#${MENU_ID}`));
}

function getButtons(root: ParentNode = getAppRoot()): HTMLButtonElement[] {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).filter((button) => !isInsideMoreMenu(button));
}

function clickByText(label: string): void {
  const wanted = normalizeLabel(label).toLowerCase();

  const button = getButtons().find((item) => {
    if (item.disabled) return false;
    return readButtonLabel(item).toLowerCase() === wanted;
  });

  button?.click();
}

function preferGuardedAuto(): void {
  // No-op: auto-mode selection is now handled by the app state directly.
}

function getPrimaryButtons(root: HTMLElement): HTMLButtonElement[] {
  return getButtons(root).filter((button) => PRIMARY.has(readButtonLabel(button)));
}

function countKnownNavButtons(element: HTMLElement): number {
  return Array.from(element.querySelectorAll<HTMLButtonElement>('button')).filter((button) => {
    const label = readButtonLabel(button);
    return PRIMARY.has(label) || OVERFLOW.has(label);
  }).length;
}

function commonAncestor(elements: HTMLElement[]): HTMLElement | null {
  if (elements.length === 0) return null;

  let candidate: HTMLElement | null = elements[0].parentElement;

  while (candidate) {
    if (elements.every((element) => candidate?.contains(element))) {
      return candidate;
    }

    candidate = candidate.parentElement;
  }

  return null;
}

function findNavRoot(): HTMLElement | null {
  const root = getAppRoot();

  const explicitNav = Array.from(
    root.querySelectorAll<HTMLElement>('nav, header, [role="navigation"], [data-role="primary-nav"], [data-mobile-nav], [data-sovereign-mobile-nav]'),
  ).find((candidate) => getPrimaryButtons(candidate).length >= 2);

  if (explicitNav) return explicitNav;

  const primaryButtons = getPrimaryButtons(root);
  if (primaryButtons.length < 2) {
    return document.querySelector<HTMLElement>('#root > div.min-h-screen > div:nth-of-type(1)');
  }

  const ancestor = commonAncestor(primaryButtons);
  if (!ancestor || ancestor === document.body || ancestor === root) {
    return document.querySelector<HTMLElement>('#root > div.min-h-screen > div:nth-of-type(1)');
  }

  let best: HTMLElement = ancestor;
  let cursor: HTMLElement | null = primaryButtons[0].parentElement;

  while (cursor && cursor !== ancestor.parentElement) {
    if (primaryButtons.every((button) => cursor?.contains(button)) && countKnownNavButtons(cursor) >= primaryButtons.length) {
      best = cursor;
      break;
    }

    cursor = cursor.parentElement;
  }

  return best;
}

function restoreManagedButtons(root: ParentNode = document): void {
  for (const button of Array.from(root.querySelectorAll<HTMLButtonElement>('button[data-sovereign-more-menu-hidden="1"]'))) {
    button.style.display = button.dataset.sovereignMoreMenuPreviousDisplay ?? '';
    delete button.dataset.sovereignMoreMenuHidden;
    delete button.dataset.sovereignMoreMenuPreviousDisplay;
  }
}

function removeMenus(root: ParentNode = document): void {
  for (const menu of Array.from(root.querySelectorAll<HTMLElement>(`#${MENU_ID}`))) {
    menu.remove();
  }
}

function removeMenusOutside(nav: HTMLElement): void {
  for (const menu of Array.from(document.querySelectorAll<HTMLElement>(`#${MENU_ID}`))) {
    if (menu.parentElement !== nav) menu.remove();
  }
}

function applyMobileButtonVisibility(nav: HTMLElement): void {
  for (const button of getButtons(nav)) {
    const label = readButtonLabel(button);

    if (!label) continue;

    if (PRIMARY.has(label)) {
      if (button.dataset.sovereignMoreMenuHidden === '1') {
        button.style.display = button.dataset.sovereignMoreMenuPreviousDisplay ?? '';
        delete button.dataset.sovereignMoreMenuHidden;
        delete button.dataset.sovereignMoreMenuPreviousDisplay;
      }

      continue;
    }

    if (!OVERFLOW.has(label)) continue;

    if (button.dataset.sovereignMoreMenuHidden !== '1') {
      button.dataset.sovereignMoreMenuPreviousDisplay = button.style.display;
      button.dataset.sovereignMoreMenuHidden = '1';
    }

    button.style.display = 'none';
  }
}

function createMenu(): HTMLDivElement {
  const box = document.createElement('div');
  box.id = MENU_ID;
  box.style.gridColumn = '1 / -1';
  box.style.width = '100%';

  const select = document.createElement('select');
  select.setAttribute('aria-label', 'Mehr Bereiche');
  select.style.cssText =
    'width:100%;min-height:2.6rem;border:1px solid rgba(148,163,184,.25);border-radius:.85rem;background:rgba(15,23,42,.86);color:#e2e8f0;padding:.5rem .7rem;font-weight:850';

  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Mehr Bereiche: Logs, Speicher, Checks...';
  select.appendChild(placeholder);

  for (const label of OPTIONS) {
    const option = document.createElement('option');
    option.value = label;
    option.textContent = label;
    select.appendChild(option);
  }

  select.addEventListener('change', (event) => {
    const target = event.currentTarget as HTMLSelectElement;
    const value = normalizeLabel(target.value);
    if (!value) return;
    clickByText(value);
    target.value = '';
  });

  box.appendChild(select);
  return box;
}

function applyMobileMoreMenu(): void {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  if (!isMobileViewport()) {
    restoreManagedButtons();
    removeMenus();
    return;
  }

  const nav = findNavRoot();
  if (!nav) return;

  removeMenusOutside(nav);
  applyMobileButtonVisibility(nav);

  if (!nav.querySelector(`#${MENU_ID}`)) nav.appendChild(createMenu());
}

function scheduleMobileMoreMenu(): void {
  if (typeof window === 'undefined') return;
  const win = runtimeWindow();

  if (win.__sovereignMoreMenuRaf) window.cancelAnimationFrame(win.__sovereignMoreMenuRaf);
  if (win.__sovereignMoreMenuTimer) window.clearTimeout(win.__sovereignMoreMenuTimer);

  win.__sovereignMoreMenuRaf = window.requestAnimationFrame(() => {
    win.__sovereignMoreMenuRaf = undefined;
    applyMobileMoreMenu();
  });

  win.__sovereignMoreMenuTimer = window.setTimeout(() => {
    win.__sovereignMoreMenuTimer = undefined;
    applyMobileMoreMenu();
  }, 120);
}

function installFallbackLoop(): void {
  const win = runtimeWindow();
  if (win.__sovereignMoreMenuFallbackInterval) return;
  win.__sovereignMoreMenuFallbackRuns = 0;
  win.__sovereignMoreMenuFallbackInterval = window.setInterval(() => {
    if (!isMobileViewport()) {
      if (win.__sovereignMoreMenuFallbackInterval) window.clearInterval(win.__sovereignMoreMenuFallbackInterval);
      win.__sovereignMoreMenuFallbackInterval = undefined;
      return;
    }

    win.__sovereignMoreMenuFallbackRuns = (win.__sovereignMoreMenuFallbackRuns ?? 0) + 1;
    applyMobileMoreMenu();

    if (win.__sovereignMoreMenuFallbackRuns >= 10 && win.__sovereignMoreMenuFallbackInterval) {
      window.clearInterval(win.__sovereignMoreMenuFallbackInterval);
      win.__sovereignMoreMenuFallbackInterval = undefined;
    }
  }, 500);
}

export function installMobileMoreMenu(): void {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  const win = runtimeWindow();
  if (win.__sovereignMoreMenuInstalled) return;
  win.__sovereignMoreMenuInstalled = true;

  scheduleMobileMoreMenu();
  installFallbackLoop();

  if (!win.__sovereignMoreMenuObserver && document.body) {
    win.__sovereignMoreMenuObserver = new MutationObserver(scheduleMobileMoreMenu);
    win.__sovereignMoreMenuObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'hidden', 'style', 'aria-label', 'title'],
    });
  }

  if (!win.__sovereignMoreMenuMedia && typeof window.matchMedia === 'function') {
    const media = window.matchMedia(MOBILE_QUERY);
    win.__sovereignMoreMenuMedia = media;
    media.addEventListener?.('change', scheduleMobileMoreMenu);
  }
}

// Compatibility for older Android WebView injected helpers.
export const __sovereignMobileMoreMenuCompatibility = {
  clickByText,
  preferGuardedAuto,
};
