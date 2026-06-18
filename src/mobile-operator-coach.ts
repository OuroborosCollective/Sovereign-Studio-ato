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

function text(): string {
  return document.body?.innerText ?? '';
}

function hasAny(source: string, tokens: string[]): boolean {
  const lower = source.toLowerCase();
  return tokens.some((token) => lower.includes(token.toLowerCase()));
}

function readCoachState(): CoachState {
  const source = text();
  const thinking = hasAny(source, ['läuft', 'running', 'busy', 'in progress', 'is building', 'is watching']);

  if (hasAny(source, ['failed', 'error', 'fehlgeschlagen', 'critical'])) {
    return {
      lamp: 'red',
      title: 'Ich sehe einen blockierenden Fehler',
      message: 'Keine Sorge. Oeffne Repair oder Monitor, dann fuehre ich dich durch den naechsten Fix.',
      action: 'Bitte Repair oder Monitor pruefen.',
      thinking: false,
    };
  }

  if (thinking) {
    return {
      lamp: 'green',
      title: 'Ich arbeite gerade',
      message: 'Ich pruefe den aktuellen Schritt. Bleib kurz hier, ich melde mich gleich.',
      action: 'Bitte warten.',
      thinking: true,
    };
  }

  if (hasAny(source, ['repo fehlt', 'repo snapshot required', 'repository snapshot is not ready', 'noch kein echtes repo'])) {
    return {
      lamp: 'yellow',
      title: 'Ich brauche zuerst dein Repository',
      message: 'Trage die Repository URL ein und tippe auf 1 · Load Repo.',
      action: 'Repo laden.',
      thinking: false,
    };
  }

  if (hasAny(source, ['platzhalter', 'concrete mission', 'konkreten auftrag'])) {
    return {
      lamp: 'yellow',
      title: 'Ich brauche einen klaren Auftrag',
      message: 'Schreibe kurz, was ich fuer dich verbessern soll. Danach Vorschlag analysieren.',
      action: 'Builder oeffnen.',
      thinking: false,
    };
  }

  if (hasAny(source, ['generated files review', 'pre-publish review', 'files / diff'])) {
    return {
      lamp: 'green',
      title: 'Ich habe etwas zum Pruefen',
      message: 'Schau dir Files und Diff an. Danach kannst du bewusst weitergehen.',
      action: 'Files und Diff pruefen.',
      thinking: false,
    };
  }

  return {
    lamp: 'yellow',
    title: 'Ich bin bereit und warte auf dich',
    message: 'Starte mit Repo. Danach fuehre ich dich Schritt fuer Schritt weiter.',
    action: 'Repo oeffnen.',
    thinking: false,
  };
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${ROOT_ID} {
      position: fixed;
      left: calc(0.6rem + env(safe-area-inset-left, 0px));
      right: calc(0.6rem + env(safe-area-inset-right, 0px));
      bottom: calc(0.65rem + env(safe-area-inset-bottom, 0px));
      z-index: 2147483000;
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 1.15rem;
      background: rgba(2, 6, 23, 0.92);
      box-shadow: 0 1rem 2.5rem rgba(0,0,0,0.42);
      color: #e2e8f0;
      backdrop-filter: blur(18px);
      overflow: hidden;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
    }
    #${ROOT_ID}.collapsed .coach-body { display: none; }
    #${ROOT_ID} .coach-head {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      padding: 0.7rem 0.8rem;
    }
    #${ROOT_ID} .coach-bot {
      display: grid;
      place-items: center;
      width: 2.35rem;
      height: 2.35rem;
      border-radius: 0.8rem;
      border: 1px solid rgba(34, 211, 238, 0.35);
      background: rgba(8, 47, 73, 0.7);
      font-size: 1.3rem;
      flex: 0 0 auto;
    }
    #${ROOT_ID} .coach-lamp {
      width: 0.7rem;
      height: 0.7rem;
      border-radius: 999px;
      box-shadow: 0 0 1rem currentColor;
      flex: 0 0 auto;
    }
    #${ROOT_ID}.green .coach-lamp { color: #34d399; background: #34d399; }
    #${ROOT_ID}.yellow .coach-lamp { color: #fbbf24; background: #fbbf24; }
    #${ROOT_ID}.red .coach-lamp { color: #fb7185; background: #fb7185; }
    #${ROOT_ID} .coach-title { font-weight: 900; color: #f8fafc; font-size: 0.86rem; line-height: 1.15; }
    #${ROOT_ID} .coach-action { color: #a5b4fc; font-size: 0.72rem; font-weight: 800; margin-top: 0.1rem; }
    #${ROOT_ID} .coach-toggle { margin-left: auto; border: 1px solid rgba(148,163,184,.28); border-radius: .7rem; background: rgba(15,23,42,.85); color: #e2e8f0; padding: .35rem .55rem; font-size: .72rem; }
    #${ROOT_ID} .coach-body { border-top: 1px solid rgba(148,163,184,.16); padding: 0.7rem 0.8rem 0.8rem; }
    #${ROOT_ID} .coach-message { color: #cbd5e1; font-size: 0.78rem; line-height: 1.35; }
    #${ROOT_ID} .coach-buttons { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .4rem; margin-top: .65rem; }
    #${ROOT_ID} .coach-buttons button { border: 1px solid rgba(148,163,184,.24); border-radius: .75rem; background: rgba(15,23,42,.9); color: #e2e8f0; padding: .45rem .25rem; font-size: .68rem; font-weight: 800; }
    #${ROOT_ID} .dots::after { content: ''; animation: sovereignDots 1.2s steps(4, end) infinite; }
    @keyframes sovereignDots { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75%, 100% { content: '...'; } }
    @media (min-width: 760px) { #${ROOT_ID} { left: auto; width: min(28rem, calc(100vw - 1.2rem)); } }
  `;
  document.head.appendChild(style);
}

function clickNav(label: string): void {
  const buttons = Array.from(document.querySelectorAll('button'));
  const button = buttons.find((item) => (item.textContent ?? '').trim().toLowerCase().includes(label.toLowerCase()));
  button?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function renderCoach(): void {
  installStyle();
  let root = document.getElementById(ROOT_ID);
  if (!root) {
    root = document.createElement('aside');
    root.id = ROOT_ID;
    document.body.appendChild(root);
  }

  const collapsed = root.classList.contains('collapsed');
  const state = readCoachState();
  root.className = `${collapsed ? 'collapsed ' : ''}${state.lamp}`;
  root.innerHTML = `
    <div class="coach-head">
      <div class="coach-bot">🤖</div>
      <span class="coach-lamp"></span>
      <div style="min-width:0; flex:1;">
        <div class="coach-title">${state.title}${state.thinking ? '<span class="dots"></span>' : ''}</div>
        <div class="coach-action">${state.action}</div>
      </div>
      <button class="coach-toggle" type="button">${collapsed ? 'zeigen' : 'klein'}</button>
    </div>
    <div class="coach-body">
      <div class="coach-message">${state.message}</div>
      <div class="coach-buttons">
        <button type="button" data-go="repo">Repo</button>
        <button type="button" data-go="builder">Builder</button>
        <button type="button" data-go="files">Files</button>
        <button type="button" data-go="monitor">Monitor</button>
      </div>
    </div>
  `;

  root.querySelector('.coach-toggle')?.addEventListener('click', () => {
    root?.classList.toggle('collapsed');
    renderCoach();
  });
  root.querySelector('[data-go="repo"]')?.addEventListener('click', () => clickNav('Repo'));
  root.querySelector('[data-go="builder"]')?.addEventListener('click', () => clickNav('Builder'));
  root.querySelector('[data-go="files"]')?.addEventListener('click', () => clickNav('Files'));
  root.querySelector('[data-go="monitor"]')?.addEventListener('click', () => clickNav('Live Monitor'));
}

export function installMobileOperatorCoach(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  window.setTimeout(renderCoach, 600);
  window.setInterval(renderCoach, 1400);
}
