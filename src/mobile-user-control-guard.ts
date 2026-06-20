const FULL_AUTO_VALUE = 'full-auto-draft-pr';
const MANUAL_VALUE = 'manual';
const USER_ALLOW_MS = 10 * 60 * 1000;
const REVIEW_TARGETS = new Set(['files', 'diff']);
const PACKAGE_MISSING_TOKENS = [
  'build a sovereign package first',
  'noch kein sovereign-paket',
  'noch kein sovereign paket',
  'noch kein package',
  'before creating a draft pr',
];

type GuardWindow = Window &
  typeof globalThis & {
    __sovereignUserControlGuardInstalled?: boolean;
    __sovereignFullAutoUserAllowedUntil?: number;
    __sovereignUserControlGuardObserver?: MutationObserver;
    __sovereignUserControlGuardTimer?: number;
  };

function runtimeWindow(): GuardWindow {
  return window as GuardWindow;
}

function normalize(value: string | null | undefined): string {
  return (value ?? '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function pageText(): string {
  return normalize(document.body?.textContent ?? '');
}

function packageStillMissing(): boolean {
  const text = pageText();
  return PACKAGE_MISSING_TOKENS.some((token) => text.includes(token));
}

function isAutomationSelect(element: EventTarget | null): element is HTMLSelectElement {
  if (!(element instanceof HTMLSelectElement)) return false;
  return Array.from(element.options).some((option) => option.value === FULL_AUTO_VALUE)
    && Array.from(element.options).some((option) => option.value === MANUAL_VALUE);
}

function setSelectValue(select: HTMLSelectElement, value: string): void {
  if (select.value === value) return;
  select.value = value;
  select.dispatchEvent(new Event('input', { bubbles: true }));
  select.dispatchEvent(new Event('change', { bubbles: true }));
}

function readButtonLabel(button: HTMLButtonElement): string {
  return normalize(button.textContent || button.getAttribute('aria-label') || button.title);
}

function shouldBlockProgrammaticReviewClick(event: Event): boolean {
  if (event.isTrusted) return false;
  const button = event.target instanceof Element ? event.target.closest('button') : null;
  if (!(button instanceof HTMLButtonElement)) return false;
  if (!REVIEW_TARGETS.has(readButtonLabel(button))) return false;
  return packageStillMissing();
}

function enforceAutomationSelects(): void {
  const state = runtimeWindow();
  const allowUntil = state.__sovereignFullAutoUserAllowedUntil ?? 0;
  const userAllowed = Date.now() < allowUntil;

  for (const select of Array.from(document.querySelectorAll<HTMLSelectElement>('select'))) {
    if (!isAutomationSelect(select)) continue;
    if (select.value === FULL_AUTO_VALUE && !userAllowed) {
      setSelectValue(select, MANUAL_VALUE);
    }
  }
}

function scheduleEnforce(): void {
  const state = runtimeWindow();
  if (state.__sovereignUserControlGuardTimer) return;
  state.__sovereignUserControlGuardTimer = window.setTimeout(() => {
    state.__sovereignUserControlGuardTimer = undefined;
    enforceAutomationSelects();
  }, 0);
}

function installChangeListener(): void {
  document.addEventListener(
    'change',
    (event) => {
      if (!isAutomationSelect(event.target)) return;
      const state = runtimeWindow();
      if (event.isTrusted && event.target.value === FULL_AUTO_VALUE) {
        state.__sovereignFullAutoUserAllowedUntil = Date.now() + USER_ALLOW_MS;
        return;
      }
      if (event.isTrusted && event.target.value !== FULL_AUTO_VALUE) {
        state.__sovereignFullAutoUserAllowedUntil = 0;
      }
      scheduleEnforce();
    },
    true,
  );
}

function installReviewClickBlocker(): void {
  document.addEventListener(
    'click',
    (event) => {
      if (!shouldBlockProgrammaticReviewClick(event)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    },
    true,
  );
}

function installObserver(): void {
  const state = runtimeWindow();
  if (state.__sovereignUserControlGuardObserver || typeof MutationObserver === 'undefined') return;
  state.__sovereignUserControlGuardObserver = new MutationObserver(scheduleEnforce);
  state.__sovereignUserControlGuardObserver.observe(document.body, { childList: true, subtree: true });
}

export function installMobileUserControlGuard(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const state = runtimeWindow();
  if (state.__sovereignUserControlGuardInstalled) {
    scheduleEnforce();
    return;
  }

  state.__sovereignUserControlGuardInstalled = true;
  state.__sovereignFullAutoUserAllowedUntil = 0;
  installChangeListener();
  installReviewClickBlocker();
  installObserver();
  enforceAutomationSelects();
  window.setTimeout(enforceAutomationSelects, 250);
  window.setTimeout(enforceAutomationSelects, 900);
}
