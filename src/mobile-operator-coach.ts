type CoachLamp = 'green' | 'yellow' | 'red';

interface CoachState {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
}

const STYLE_ID = 'sovereign-mobile-coach-style';
const ROOT_ID = 'sovereign-mobile-coach';

function pageText(): string {
  return document.body?.textContent ?? '';
}

function hasAny(source: string, tokens: string[]): boolean {
  const lower = source.toLowerCase();
  return tokens.some((token) => lower.includes(token.toLowerCase()));
}

function readCoachState(): CoachState {
  const source = pageText();
  const thinking = hasAny(source, ['läuft', 'running', 'busy', 'in progress', 'is building', 'is watching']);

  if (hasAny(source, ['failed', 'error', 'fehlgeschlagen', 'critical'])) {
    return { lamp: 'red', title: 'Ich sehe einen Stopper', message: 'Wir halten kurz an. Der naechste Schritt steht im Monitor oder Repair.', action: 'Repair oder Monitor pruefen.', thinking: false };
  }

  if (thinking) {
    return { lamp: 'green', title: 'Ich arbeite gerade', message: 'Ich analysiere den Ablauf. Du musst jetzt nichts klicken.', action: 'Bitte warten.', thinking: true };
  }

  if (hasAny(source, ['repo fehlt', 'repo snapshot required', 'repository snapshot is not ready', 'noch kein echtes repo'])) {
    return { lamp: 'yellow', title: 'Ich brauche zuerst dein Repo', message: 'Trage die Repository URL ein und tippe auf 1 · Load Repo.', action: 'Repo laden.', thinking: false };
  }

  if (hasAny(source, ['platzhalter', 'konkreten auftrag', 'concrete mission'])) {
    return { lamp: 'yellow', title: 'Ich brauche deinen Wunsch', message: 'Schreibe kurz, was ich verbessern soll. Danach analysieren wir den Auftrag.', action: 'Builder oeffnen.', thinking: false };
  }

  if (hasAny(source, ['generated files review', 'pre-publish review', 'generated file'])) {
    return { lamp: 'green', title: 'Ich habe Ergebnis-Dateien', message: 'Pruefe Files und Diff. Danach kannst du bewusst weitergehen.', action: 'Files und Diff pruefen.', thinking: false };
  }

  return { lamp: 'yellow', title: 'Ich warte auf den Start', message: 'Fang mit Repo an. Ich fuehre dich dann Schritt fuer Schritt weiter.', action: 'Repo oeffnen.', thinking: false };
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${ROOT_ID} { border: 1px solid rgba(34,211,238,.28); border-radius: 1.25rem; background: linear-gradient(135deg, rgba(2,6,23,.94), rgba(15,23,42,.88)); color: #e2e8f0; overflow: hidden; box-shadow: 0 .9rem 2rem rgba(0,0,0,.22); font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    #${ROOT_ID}.green { border-color: rgba(52,211,153,.38); }
    #${ROOT_ID}.yellow { border-color: rgba(251,191,36,.42); }
    #${ROOT_ID}.red { border-color: rgba(251,113,133,.48); }
    #${ROOT_ID} .coach-head { display: flex; align-items: center; gap: .7rem; padding: .85rem .9rem; }
    #${ROOT_ID} .coach-bot { display: grid; place-items: center; width: 2.65rem; height: 2.65rem; border-radius: .9rem; border: 1px solid rgba(34,211,238,.38); background: rgba(8,47,73,.72); font-size: 1.45rem; }
    #${ROOT_ID} .coach-lamp { width: .78rem; height: .78rem; border-radius: 999px; box-shadow: 0 0 1rem currentColor; }
    #${ROOT_ID}.green .coach-lamp { color: #34d399; background: #34d399; }
    #${ROOT_ID}.yellow .coach-lamp { color: #fbbf24; background: #fbbf24; }
    #${ROOT_ID}.red .coach-lamp { color: #fb7185; background: #fb7185; }
    #${ROOT_ID} .coach-title { font-size: .95rem; font-weight: 950; color: #f8fafc; line-height: 1.1; }
    #${ROOT_ID} .coach-action { color: #a5b4fc; font-size: .75rem; font-weight: 850; margin-top: .15rem; }
    #${ROOT_ID} .coach-body { border-top: 1px solid rgba(148,163,184,.14); padding: .82rem .9rem .92rem; }
    #${ROOT_ID} .coach-message { font-size: .82rem; line-height: 1.38; color: #cbd5e1; }
    #${ROOT_ID} .coach-terminal { margin-top: .7rem; border: 1px solid rgba(34,211,238,.18); border-radius: .9rem; background: rgba(0,0,0,.35); padding: .7rem; color: #67e8f9; font: 700 .74rem/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
    #${ROOT_ID} .prompt { color: #a7f3d0; }
    #${ROOT_ID} .coach-buttons { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .42rem; margin-top: .7rem; }
    #${ROOT_ID} .coach-buttons button { border: 1px solid rgba(148,163,184,.25); border-radius: .82rem; background: rgba(15,23,42,.86); color: #e2e8f0; padding: .5rem .35rem; font-size: .72rem; font-weight: 850; }
    #${ROOT_ID} .dots::after { content: ''; animation: sovereignDots 1.2s steps(4, end) infinite; }
    @keyframes sovereignDots { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75%,100% { content: '...'; } }
  `;
  document.head.appendChild(style);
}

function clickNav(label: string): void {
  const button = Array.from(document.querySelectorAll('button')).find((item) => (item.textContent ?? '').trim().toLowerCase() === label.toLowerCase());
  button?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function appShell(): HTMLElement | null {
  return document.querySelector('#root > div.min-h-screen');
}

function navShell(): Element | null {
  return document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)');
}

function renderCoach(): void {
  installStyle();
  const shell = appShell();
  const nav = navShell();
  if (!shell || !nav) return;
  let root = document.getElementById(ROOT_ID);
  if (!root) {
    root = document.createElement('section');
    root.id = ROOT_ID;
    nav.insertAdjacentElement('afterend', root);
  }

  const state = readCoachState();
  const mode = state.thinking ? 'matrix-work' : state.lamp === 'red' ? 'repair-log' : state.title.includes('Ergebnis') ? 'review-log' : 'nocode-plan';
  root.className = state.lamp;
  root.innerHTML = `
    <div class="coach-head"><div class="coach-bot">🤖</div><span class="coach-lamp"></span><div style="min-width:0;flex:1"><div class="coach-title">Sovereign Bot · ${state.title}${state.thinking ? '<span class="dots"></span>' : ''}</div><div class="coach-action">${state.action}</div></div></div>
    <div class="coach-body"><div class="coach-message">${state.message}</div><div class="coach-terminal"><span class="prompt">${mode} $</span> ${state.message}${state.thinking ? '<span class="dots"></span>' : ''}</div><div class="coach-buttons"><button data-go="Repo">Repo</button><button data-go="Builder">Planen</button><button data-go="Files">Dateien</button><button data-go="Live Monitor">Logs</button></div></div>
  `;
  root.querySelectorAll('[data-go]').forEach((button) => button.addEventListener('click', () => clickNav((button as HTMLElement).dataset.go ?? 'Repo')));
}

export function installMobileOperatorCoach(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  window.setTimeout(renderCoach, 700);
  window.setInterval(renderCoach, 1400);
}
