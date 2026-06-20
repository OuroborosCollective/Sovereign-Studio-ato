const MENU_ID = 'sovereign-more-menu';
const MOBILE_QUERY = '(max-width: 767px)';
const AUTO_MODE_VALUE = 'full-auto-draft-pr';

const PRIMARY_LABELS = ['Repo', 'Builder', 'Files', 'Diff'] as const;

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
  const select = Array.from(document.querySelectorAll<HTMLSelectElement>('select')).find((item) =>
    Array.from(item.options).some((option) => option.value === AUTO_MODE_VALUE),
  );

  if (!select || select.value === AUTO_MODE_VALUE) return;

  select.value = AUTO_MODE_VALUE;
  select.dispatchEvent(new Event('input', { bubbles: true }));
  select.dispatchEvent(new Event('change', { bubbles: true }));
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

function ensureSingleMenu(nav: HTMLElement): void {
  removeMenusOutside(nav);

  const menus = Array.from(nav.querySelectorAll<HTMLElement>(`#${MENU_ID}`));
  const [first, ...duplicates] = menus;

  for (const duplicate of duplicates) duplicate.remove();
  if (!first) nav.appendChild(createMenu());
}

function installNow(): void {
  preferGuardedAuto();

  const nav = findNavRoot();

  if (!isMobileViewport()) {
    restoreManagedButtons();
    removeMenus();
    return;
  }

  if (!nav) return;

  applyMobileButtonVisibility(nav);
  ensureSingleMenu(nav);
}

function scheduleInstall(): void {
  const state = runtimeWindow();

  if (state.__sovereignMoreMenuTimer) return;

  state.__sovereignMoreMenuTimer = window.setTimeout(() => {
    state.__sovereignMoreMenuTimer = undefined;
    installNow();
  }, 0);
}

function installObserver(): void {
  const state = runtimeWindow();

  if (state.__sovereignMoreMenuObserver || typeof MutationObserver === 'undefined') return;

  state.__sovereignMoreMenuObserver = new MutationObserver(() => {
    scheduleInstall();
  });

  state.__sovereignMoreMenuObserver.observe(document.body, {
    childList: true,
    subtree: true,
  });
}

function installMediaListener(): void {
  const state = runtimeWindow();

  if (state.__sovereignMoreMenuMedia || typeof window.matchMedia !== 'function') return;

  const media = window.matchMedia(MOBILE_QUERY);
  state.__sovereignMoreMenuMedia = media;

  media.addEventListener('change', scheduleInstall);
}

function installBoundedFallback(): void {
  const state = runtimeWindow();

  if (state.__sovereignMoreMenuFallbackInterval) return;

  state.__sovereignMoreMenuFallbackRuns = 0;

  state.__sovereignMoreMenuFallbackInterval = window.setInterval(() => {
    state.__sovereignMoreMenuFallbackRuns = (state.__sovereignMoreMenuFallbackRuns ?? 0) + 1;
    scheduleInstall();

    if (state.__sovereignMoreMenuFallbackRuns >= 8 && state.__sovereignMoreMenuFallbackInterval) {
      window.clearInterval(state.__sovereignMoreMenuFallbackInterval);
      state.__sovereignMoreMenuFallbackInterval = undefined;
    }
  }, 750);
}

export function installMobileMoreMenu(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const state = runtimeWindow();

  if (state.__sovereignMoreMenuInstalled) {
    installNow();
    scheduleInstall();
    return;
  }

  state.__sovereignMoreMenuInstalled = true;

  installObserver();
  installMediaListener();
  installBoundedFallback();

  installNow();
  scheduleInstall();
  window.setTimeout(scheduleInstall, 250);
  window.setTimeout(scheduleInstall, 800);
}
