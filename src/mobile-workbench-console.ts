import { decideMobileWorkflow } from './mobile-workflow-orchestrator';

const ROOT_ID = 'sovereign-mobile-workbench-console';
const STYLE_ID = 'sovereign-mobile-workbench-style';
let lastTarget = '';
let lastTargetAt = 0;

function pageText(): string {
  return document.body?.textContent ?? '';
}

function goTo(label: string): void {
  const now = Date.now();
  if (lastTarget === label && now - lastTargetAt < 2400) return;
  const button = Array.from(document.querySelectorAll('button')).find((item) => (item.textContent ?? '').trim().toLowerCase() === label.toLowerCase());
  if (!button) return;
  lastTarget = label;
  lastTargetAt = now;
  button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function anchorShell(): Element | null {
  return document.getElementById('sovereign-mobile-coach') ?? document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)');
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

function render(): void {
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
  if (decision.autoOpenTarget && decision.targetNav) goTo(decision.targetNav);
  root.className = decision.lamp;
  const dots = decision.mode === 'matrix-work' ? '<span class="dots"></span>' : '';
  root.innerHTML = `<div class="head"><div><div class="title">Live Arbeitsmonitor · ${decision.title}${dots}</div><div class="mode">${decision.mode}</div></div><div>${decision.targetNav ? `→ ${decision.targetNav}` : 'bereit'}</div></div><div class="body"><div class="summary">${decision.summary}</div><pre>${decision.lines.join('\n')}</pre></div>`;
}

export function installMobileWorkbenchConsole(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  window.setTimeout(render, 950);
  window.setInterval(render, 1500);
}
