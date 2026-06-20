import { assertMobileWorkflowDecisionValid, decideMobileWorkflow, type MobileWorkflowOrchestratorDecision } from './mobile-workflow-orchestrator';

const ROOT_ID = 'sovereign-mobile-workbench-console';
const STYLE_ID = 'sovereign-mobile-workbench-style';
const MOBILE_COACH_ID = 'sovereign-mobile-coach';
const MOBILE_SETUP_ID = 'sovereign-mobile-setup-drawer';
const TEXT_NODE = 4;
const ACCEPT = 1;
const REJECT = 2;
const AUTO_OPEN_COOLDOWN_MS = 6_000;

let lastTarget = '';
let lastTargetAt = 0;
let lastDecisionSignature = '';

function ignoredSelector(): string {
  return `#${ROOT_ID}, #${MOBILE_COACH_ID}, #${MOBILE_SETUP_ID}, #${STYLE_ID}, script, style, noscript`;
}

function closestElement(node: Node): Element | null {
  return node instanceof Element ? node : node.parentElement;
}

function shouldReadTextNode(node: Node): number {
  const element = closestElement(node);
  if (!element) return REJECT;
  return element.closest(ignoredSelector()) ? REJECT : ACCEPT;
}

export function collectMobileWorkbenchVisibleText(root: ParentNode | null = document.body): string {
  if (!root || typeof document === 'undefined') return '';

  const parts: string[] = [];
  const walker = document.createTreeWalker(
    root,
    TEXT_NODE,
    { acceptNode: shouldReadTextNode },
  );

  let node = walker.nextNode();
  while (node) {
    const value = node.nodeValue?.trim();
    if (value) parts.push(value);
    node = walker.nextNode();
  }

  return parts.join('\n');
}

function pageText(): string {
  return collectMobileWorkbenchVisibleText(document.body);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function findNavButton(label: string): HTMLButtonElement | null {
  const wanted = label.toLowerCase();
  return Array.from(document.querySelectorAll('button')).find((item) => {
    if (item.closest(ignoredSelector())) return false;
    return (item.textContent ?? '').trim().toLowerCase() === wanted;
  }) ?? null;
}

function goTo(label: string): void {
  const now = Date.now();
  if (lastTarget === label && now - lastTargetAt < AUTO_OPEN_COOLDOWN_MS) return;
  const button = findNavButton(label);
  if (!button) return;
  lastTarget = label;
  lastTargetAt = now;
  button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function anchorShell(): Element | null {
  return document.getElementById(MOBILE_COACH_ID) ?? document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)');
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${ROOT_ID} { margin-top:.8rem; border:1px solid rgba(34,211,238,.24); border-radius:1.1rem; background:rgba(2,6,23,.9); color:#e2e8f0; overflow:hidden; }
    #${ROOT_ID}.green { border-color:rgba(52,211,153,.38); }
    #${ROOT_ID}.yellow { border-color:rgba(251,191,36,.38); }
    #${ROOT_ID}.red { border-color:rgba(251,113,133,.45); }
    #${ROOT_ID} .head { display:flex; justify-content:space-between; gap:.75rem; padding:.72rem .85rem; border-bottom:1px solid rgba(148,163,184,.14); }
    #${ROOT_ID} .title { font-weight:950; font-size:.82rem; color:#f8fafc; }
    #${ROOT_ID} .mode { font-size:.68rem; font-weight:900; color:#67e8f9; letter-spacing:.08em; text-transform:uppercase; }
    #${ROOT_ID} .body { padding:.78rem .85rem; }
    #${ROOT_ID} .summary { color:#cbd5e1; font-size:.78rem; line-height:1.38; }
    #${ROOT_ID} pre { margin:.65rem 0 0; white-space:pre-wrap; border:1px solid rgba(34,211,238,.18); border-radius:.85rem; background:rgba(0,0,0,.42); color:#67e8f9; padding:.72rem; font:800 .72rem/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
    #${ROOT_ID} .dots::after { content:''; animation: wbDots 1.25s steps(4,end) infinite; }
    @keyframes wbDots { 0%{content:''} 25%{content:'.'} 50%{content:'..'} 75%,100%{content:'...'} }
  `;
  document.head.appendChild(style);
}

export function shouldAutoOpenWorkbenchTarget(decision: MobileWorkflowOrchestratorDecision): boolean {
  if (!decision.autoOpenTarget || !decision.targetNav) return false;
  return decision.mode === 'matrix-work' || decision.lamp === 'red';
}

function decisionSignature(decision: MobileWorkflowOrchestratorDecision): string {
  return `${decision.lamp}|${decision.mode}|${decision.title}|${decision.targetNav ?? 'none'}|${decision.lines.join('\n')}`;
}

function render(): void {
  try {
    installStyle();
    const anchor = anchorShell();
    if (!anchor) return;
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      root = document.createElement('section');
      root.id = ROOT_ID;
      anchor.insertAdjacentElement('afterend', root);
    }

    const decision = decideMobileWorkflow({ visibleText: pageText() });
    assertMobileWorkflowDecisionValid(decision);

    const signature = decisionSignature(decision);
    const changed = signature !== lastDecisionSignature;
    lastDecisionSignature = signature;

    if (changed && shouldAutoOpenWorkbenchTarget(decision)) {
      goTo(decision.targetNav as string);
    }

    root.className = decision.lamp;
    const dots = decision.mode === 'matrix-work' ? '<span class="dots"></span>' : '';
    const target = decision.targetNav ? `→ ${escapeHtml(decision.targetNav)}` : 'bereit';
    root.innerHTML = `<div class="head"><div><div class="title">Live Arbeitsmonitor · ${escapeHtml(decision.title)}${dots}</div><div class="mode">${escapeHtml(decision.mode)}</div></div><div>${target}</div></div><div class="body"><div class="summary">${escapeHtml(decision.summary)}</div><pre>${decision.lines.map(escapeHtml).join('\n')}</pre></div>`;
  } catch {
    // The workbench is guidance only. It must never break the real app runtime.
  }
}

export function installMobileWorkbenchConsole(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  window.setTimeout(render, 950);
  window.setInterval(render, 1500);
}
