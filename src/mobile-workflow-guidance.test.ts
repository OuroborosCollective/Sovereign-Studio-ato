import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installMobileMoreMenu } from './mobile-more-menu';
import { installMobileOperatorCoach } from './mobile-operator-coach';
import { installMobileSetupDrawer } from './mobile-setup-drawer';

function mountShell(extra = '') {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <h1>Sovereign Canvas Tool</h1>
        <div>
          <button>Repo</button>
          <button>Builder</button>
          <button>Files</button>
          <button>Diff</button>
          <button>Workflow</button>
          <button>Telemetry</button>
          <button>Live Monitor</button>
        </div>
        <section>Repo fehlt. Noch kein echtes Repo geladen.</section>
        <section>
          <select aria-label="Automation Mode">
            <option value="manual">Manual</option>
            <option value="auto-review">Auto Review</option>
            <option value="full-auto-draft-pr">Full Auto Draft PR</option>
          </select>
        </section>
        <section>
          <label>GitHub Repository URL<input aria-label="GitHub Repository URL" /></label>
          <label>GitHub private access<input aria-label="GitHub private access" type="password" /></label>
        </section>
        ${extra}
      </div>
    </div>
  `;
}

describe('mobile workflow guidance', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
    mountShell();
  });

  afterEach(() => {
    vi.useRealTimers();
    window.localStorage.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('moves secondary areas into a mobile more menu and prefers guarded full auto', () => {
    installMobileMoreMenu();
    vi.advanceTimersByTime(900);

    const menu = document.getElementById('sovereign-more-menu');
    expect(menu).toBeTruthy();
    expect(document.querySelector('select[aria-label="Mehr Bereiche"]')).toBeTruthy();

    const buttons = Array.from(document.querySelectorAll('button')).map((button) => ({
      label: button.textContent?.trim(),
      display: button.style.display,
    }));
    expect(buttons.find((button) => button.label === 'Repo')?.display).not.toBe('none');
    expect(buttons.find((button) => button.label === 'Builder')?.display).not.toBe('none');
    expect(buttons.find((button) => button.label === 'Telemetry')?.display).toBe('none');

    const automation = document.querySelector('select[aria-label="Automation Mode"]') as HTMLSelectElement;
    expect(automation.value).toBe('full-auto-draft-pr');
  });

  it('renders the operator coach inline after navigation with yellow setup guidance', () => {
    installMobileOperatorCoach();
    vi.advanceTimersByTime(800);

    const coach = document.getElementById('sovereign-mobile-coach');
    expect(coach).toBeTruthy();
    expect(coach?.className).toContain('yellow');
    expect(coach?.textContent).toContain('Sovereign Bot');
    expect(coach?.textContent).toContain('Repo Setup');

    const nav = document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)');
    expect(nav?.nextElementSibling).toBe(coach);
  });

  it('does not show a red stopper for harmless zero-failed runtime text', () => {
    document.body.innerHTML = '';
    mountShell('<section>Sequential Runtime Guard no active step; 0 completed step(s), 0 failed step(s). Runtime ready.</section>');

    installMobileOperatorCoach();
    vi.advanceTimersByTime(800);

    const coach = document.getElementById('sovereign-mobile-coach');
    expect(coach?.className).not.toContain('red');
    expect(coach?.textContent).not.toContain('Ich sehe einen echten Stopper');
  });

  it('shows green review guidance when generated files passed self review', () => {
    document.body.innerHTML = '';
    mountShell('<section>Generated Files Review SELF REVIEW: ACCEPTED Generated package passed self review. Learning signal: generated-output-accepted</section>');

    installMobileOperatorCoach();
    vi.advanceTimersByTime(800);

    const coach = document.getElementById('sovereign-mobile-coach');
    expect(coach?.className).toContain('green');
    expect(coach?.textContent).toContain('Ergebnis ist bereit');
  });

  it('keeps repo setup reachable from every tab through the global setup drawer', () => {
    installMobileSetupDrawer();
    vi.advanceTimersByTime(1000);

    const root = document.getElementById('sovereign-mobile-setup-drawer');
    expect(root).toBeTruthy();
    expect(root?.textContent).toContain('Repo Setup');

    (root?.querySelector('.setup-fab') as HTMLButtonElement).click();
    expect(root?.querySelector('.setup-panel')?.classList.contains('hidden')).toBe(false);

    const repo = root?.querySelector('[data-field="repoUrl"]') as HTMLInputElement;
    const access = root?.querySelector('[data-field="accessValue"]') as HTMLInputElement;
    repo.value = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';
    access.value = 'secret-value';

    (root?.querySelector('[data-action="save"]') as HTMLButtonElement).click();
    vi.advanceTimersByTime(200);

    expect((document.querySelector('input[aria-label="GitHub Repository URL"]') as HTMLInputElement).value).toBe('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
    expect((document.querySelector('input[aria-label="GitHub private access"]') as HTMLInputElement).value).toBe('secret-value');
  });
});
