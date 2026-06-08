Object.assign(window, { StrictMode: 'div' });

function setSovereignPane(pane: string) {
  if (typeof document === 'undefined') return;
  document.body.dataset.sovereignPane = pane;
  document.querySelectorAll('#sovereign-mobile-tabs button').forEach((button) => {
    (button as HTMLButtonElement).dataset.active = (button as HTMLButtonElement).dataset.pane === pane ? 'true' : 'false';
  });
}

function findButton(label: string): HTMLButtonElement | null {
  return Array.from(document.querySelectorAll('button')).find((button) =>
    (button.textContent || '').trim().toLowerCase() === label.toLowerCase()
  ) as HTMLButtonElement | null;
}

function installJobAutoDriver() {
  if (typeof document === 'undefined') return;
  if (document.body.dataset.sovereignAutoDriver === 'ready') return;
  document.body.dataset.sovereignAutoDriver = 'ready';

  document.addEventListener('click', (event) => {
    const target = event.target as HTMLElement | null;
    const button = target?.closest('button') as HTMLButtonElement | null;
    const text = (button?.textContent || '').trim().toLowerCase();
    if (text !== 'auftrag starten' && text !== 'uebernehmen') return;
    if (document.body.dataset.sovereignJobRunning === 'true') return;

    document.body.dataset.sovereignJobRunning = 'true';
    setSovereignPane('live');

    window.setTimeout(() => findButton('Pruefen')?.click(), 1800);
    window.setTimeout(() => findButton('Fix')?.click(), 3900);
    window.setTimeout(() => findButton('Pruefen')?.click(), 6200);
    window.setTimeout(() => {
      document.body.dataset.sovereignJobRunning = 'false';
      setSovereignPane('live');
    }, 8400);
  }, true);
}

function installIdeaFactory() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('sovereign-idea-factory')) return;
  const textarea = document.querySelector('textarea');
  if (!textarea) return;

  const box = document.createElement('div');
  box.id = 'sovereign-idea-factory';
  box.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin:8px 0;font-size:11px';
  const ideas = [
    'README + Update History',
    'CI Fehleranalyse',
    'Android Release Check',
  ];
  for (const idea of ideas) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.textContent = idea;
    chip.style.cssText = 'border:1px solid #ddd6fe;border-radius:999px;background:#eef2ff;color:#3730a3;padding:6px 10px;font-weight:800';
    chip.onclick = () => {
      textarea.value = idea;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    };
    box.appendChild(chip);
  }
  textarea.parentElement?.insertBefore(box, textarea.nextSibling);
}

function installMobilePaneController() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('sovereign-mobile-tabs')) return;

  const main = document.querySelector('main.flex-1.flex.overflow-hidden');
  if (!main) return;

  const style = document.createElement('style');
  style.id = 'sovereign-mobile-pane-style';
  style.textContent = `
@media (min-width: 821px) { #sovereign-mobile-tabs { display: none !important; } }
@media (max-width: 820px) and (orientation: portrait) {
  main.flex-1.flex.overflow-hidden { display: block !important; overflow-y: auto !important; padding-bottom: 52px; }
  main.flex-1.flex.overflow-hidden > section { width: 100% !important; height: calc(100vh - 108px); max-height: none !important; }
  body[data-sovereign-pane="auftrag"] main.flex-1.flex.overflow-hidden > section:nth-child(2),
  body[data-sovereign-pane="auftrag"] main.flex-1.flex.overflow-hidden > section:nth-child(3) { display: none !important; }
  body[data-sovereign-pane="live"] main.flex-1.flex.overflow-hidden > section:nth-child(1),
  body[data-sovereign-pane="live"] main.flex-1.flex.overflow-hidden > section:nth-child(3) { display: none !important; }
  body[data-sovereign-pane="log"] main.flex-1.flex.overflow-hidden > section:nth-child(1),
  body[data-sovereign-pane="log"] main.flex-1.flex.overflow-hidden > section:nth-child(2) { display: none !important; }
  #sovereign-mobile-tabs { position: fixed; left: 10px; right: 10px; bottom: 10px; z-index: 9999; display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding: 6px; border-radius: 16px; background: rgba(12, 10, 9, .9); box-shadow: 0 12px 40px rgba(0,0,0,.3); }
  #sovereign-mobile-tabs button { border: 0; border-radius: 12px; padding: 10px 8px; font-size: 11px; font-weight: 900; background: #e7e5e4; color: #292524; }
  #sovereign-mobile-tabs button[data-active="true"] { background: #4f46e5; color: white; }
}
`;
  document.head.appendChild(style);

  const tabs = document.createElement('nav');
  tabs.id = 'sovereign-mobile-tabs';
  const panes = [
    ['auftrag', 'Auftrag'],
    ['live', 'Live'],
    ['log', 'Log'],
  ] as const;

  for (const [pane, label] of panes) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.dataset.pane = pane;
    button.onclick = () => setSovereignPane(pane);
    tabs.appendChild(button);
  }

  document.body.appendChild(tabs);
  setSovereignPane(document.body.dataset.sovereignPane || 'live');
}

if (typeof window !== 'undefined') {
  window.setTimeout(() => { installMobilePaneController(); installJobAutoDriver(); installIdeaFactory(); }, 300);
  window.setTimeout(() => { installMobilePaneController(); installJobAutoDriver(); installIdeaFactory(); }, 1200);
}

export {};
