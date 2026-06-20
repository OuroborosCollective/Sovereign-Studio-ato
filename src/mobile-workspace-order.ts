type WorkspaceWindow = Window &
  typeof globalThis & {
    __sovereignMobileWorkspaceOrderInstalled?: boolean;
    __sovereignMobileWorkspaceOrderTimer?: number;
    __sovereignMobileWorkspaceOrderObserver?: MutationObserver;
  };

const COACH_ID = 'sovereign-mobile-coach';
const STYLE_ID = 'sovereign-mobile-workspace-order-style';
const ACTIVE_TITLES = [
  'repository snapshot',
  'github repo setup',
  'sovereign action builder',
  'generated files review',
  'generated file diff',
  'live monitor',
  'repo readiness',
  'file integrity',
  'scan finding',
  'workflow',
  'repair',
  'health',
  'runtime',
  'coverage',
  'pattern memory',
  'remote memory',
  'telemetry',
];

function norm(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function visible(element: Element | null | undefined): element is HTMLElement {
  if (!(element instanceof HTMLElement)) return false;
  if (element.hidden || element.getAttribute('aria-hidden') === 'true') return false;
  const style = window.getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden';
}

function appShell(): HTMLElement | null {
  return document.querySelector('#root > div.min-h-screen') ?? document.querySelector('#root > div');
}

function isCoach(element: Element): boolean {
  return element.id === COACH_ID;
}

function isTitle(element: Element): boolean {
  return element.tagName.toLowerCase() === 'h1';
}

function isPrimaryNav(element: Element): boolean {
  if (element.closest(`#${COACH_ID}`)) return false;
  const text = norm(element.textContent ?? '');
  const buttons = Array.from(element.querySelectorAll('button')).map((button) => norm(button.textContent ?? ''));
  const hasMainButtons = ['repo', 'builder', 'files', 'diff'].every((label) => buttons.includes(label));
  const hasLocalizedCoachButtons = ['repo', 'planen', 'dateien', 'logs'].every((label) => buttons.includes(label));
  return hasMainButtons || hasLocalizedCoachButtons || element.getAttribute('data-role') === 'primary-nav' || text === 'repo builder files diff';
}

function isAutomationPanel(element: Element): boolean {
  const text = norm(element.textContent ?? '');
  return text.includes('automation mode') && element.querySelector('select') !== null;
}

function isMoreMenu(element: Element): boolean {
  const text = norm(element.textContent ?? '');
  return text.includes('mehr bereiche') || text.includes('logs, speicher, checks');
}

function isActiveWorkspace(element: Element): boolean {
  if (!visible(element)) return false;
  if (isCoach(element) || isTitle(element) || isPrimaryNav(element) || isAutomationPanel(element) || isMoreMenu(element)) return false;
  const text = norm(element.textContent ?? '');
  if (!text) return false;
  return ACTIVE_TITLES.some((title) => text.includes(title));
}

function directChildren(shell: HTMLElement): HTMLElement[] {
  return Array.from(shell.children).filter((child): child is HTMLElement => child instanceof HTMLElement);
}

function findTitle(shell: HTMLElement): HTMLElement | null {
  return directChildren(shell).find(isTitle) ?? shell.querySelector('h1');
}

function findCoach(shell: HTMLElement): HTMLElement | null {
  return shell.querySelector<HTMLElement>(`#${COACH_ID}`);
}

function findPrimaryNav(shell: HTMLElement): HTMLElement | null {
  return directChildren(shell).find((child) => visible(child) && isPrimaryNav(child)) ?? null;
}

function findAutomation(shell: HTMLElement): HTMLElement | null {
  return directChildren(shell).find((child) => visible(child) && isAutomationPanel(child)) ?? null;
}

function findMoreMenu(shell: HTMLElement): HTMLElement | null {
  return directChildren(shell).find((child) => visible(child) && isMoreMenu(child)) ?? null;
}

function findActiveWorkspace(shell: HTMLElement): HTMLElement | null {
  return directChildren(shell).find(isActiveWorkspace) ?? null;
}

function moveAfter(anchor: HTMLElement, element: HTMLElement | null): HTMLElement {
  if (!element || element === anchor) return anchor;
  if (anchor.nextElementSibling !== element) anchor.insertAdjacentElement('afterend', element);
  return element;
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = [
    '#sovereign-mobile-coach + [data-sovereign-active-workspace="true"]{margin-top:1rem}',
    '[data-sovereign-active-workspace="true"]{scroll-margin-top:1rem}',
    '@media (max-width: 767px){#root > div.min-h-screen{padding-bottom:max(1rem,env(safe-area-inset-bottom,0px))}}',
  ].join('\n');
  document.head.appendChild(style);
}

export function orderMobileWorkspace(): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false;
  const shell = appShell();
  if (!shell) return false;

  installStyle();

  const title = findTitle(shell);
  const coach = findCoach(shell);
  const active = findActiveWorkspace(shell);
  const automation = findAutomation(shell);
  const nav = findPrimaryNav(shell);
  const more = findMoreMenu(shell);

  if (!title || !coach) return false;

  for (const child of directChildren(shell)) child.removeAttribute('data-sovereign-active-workspace');
  if (active) active.setAttribute('data-sovereign-active-workspace', 'true');

  let anchor = moveAfter(title, coach);
  anchor = moveAfter(anchor, active);
  anchor = moveAfter(anchor, automation);
  anchor = moveAfter(anchor, nav);
  moveAfter(anchor, more);

  return true;
}

function scheduleOrder(): void {
  const win = window as WorkspaceWindow;
  if (win.__sovereignMobileWorkspaceOrderTimer) window.clearTimeout(win.__sovereignMobileWorkspaceOrderTimer);
  win.__sovereignMobileWorkspaceOrderTimer = window.setTimeout(() => {
    win.__sovereignMobileWorkspaceOrderTimer = undefined;
    orderMobileWorkspace();
  }, 60);
}

export function installMobileWorkspaceOrder(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const win = window as WorkspaceWindow;
  if (win.__sovereignMobileWorkspaceOrderInstalled) return;
  win.__sovereignMobileWorkspaceOrderInstalled = true;

  window.setTimeout(orderMobileWorkspace, 0);
  window.setInterval(orderMobileWorkspace, 350);

  if (!win.__sovereignMobileWorkspaceOrderObserver && document.body) {
    win.__sovereignMobileWorkspaceOrderObserver = new MutationObserver(scheduleOrder);
    win.__sovereignMobileWorkspaceOrderObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'hidden', 'style', 'data-role', 'data-sovereign-active-workspace'],
    });
  }
}
