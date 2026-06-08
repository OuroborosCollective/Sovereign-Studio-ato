Object.assign(window, { StrictMode: 'div' });

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

  function setPane(pane: string) {
    document.body.dataset.sovereignPane = pane;
    for (const button of Array.from(tabs.querySelectorAll('button'))) {
      button.dataset.active = button.dataset.pane === pane ? 'true' : 'false';
    }
  }

  for (const [pane, label] of panes) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.dataset.pane = pane;
    button.onclick = () => setPane(pane);
    tabs.appendChild(button);
  }

  document.body.appendChild(tabs);
  setPane(document.body.dataset.sovereignPane || 'live');
}

if (typeof window !== 'undefined') {
  window.setTimeout(installMobilePaneController, 300);
  window.setTimeout(installMobilePaneController, 1200);
}

export {};
