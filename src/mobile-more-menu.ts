const MENU_ID = 'sovereign-more-menu';
const OPTIONS = ['Workflow', 'Repair', 'Remote Memory', 'Pattern Memory', 'Telemetry', 'Live Monitor', 'Readiness', 'Integrity', 'Findings', 'Health', 'Runtime', 'Coverage'];

function clickByText(label: string): void {
  const button = Array.from(document.querySelectorAll('button')).find((item) => (item.textContent ?? '').trim().toLowerCase() === label.toLowerCase());
  button?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function install(): void {
  const nav = document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)');
  if (!nav || document.getElementById(MENU_ID)) return;
  const box = document.createElement('div');
  box.id = MENU_ID;
  box.style.gridColumn = '1 / -1';
  box.innerHTML = `<select aria-label="Mehr Bereiche" style="width:100%;min-height:2.6rem;border:1px solid rgba(148,163,184,.25);border-radius:.85rem;background:rgba(15,23,42,.86);color:#e2e8f0;padding:.5rem .7rem;font-weight:850"><option value="">Mehr Bereiche: Logs, Speicher, Checks...</option>${OPTIONS.map((label) => `<option value="${label}">${label}</option>`).join('')}</select>`;
  nav.appendChild(box);
  box.querySelector('select')?.addEventListener('change', (event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (value) clickByText(value);
  });
}

export function installMobileMoreMenu(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  window.setTimeout(install, 800);
  window.setInterval(install, 2000);
}
