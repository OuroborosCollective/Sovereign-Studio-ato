import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installMobileSetupDrawer } from './mobile-setup-drawer';

describe('mobile setup drawer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <div id="root">
        <div class="min-h-screen">
          <div><button type="button">Repo</button></div>
          <section>
            <input aria-label="GitHub Repository URL" />
            <input aria-label="GitHub private access" />
            <button type="button">1 · Load Repo</button>
          </section>
        </div>
      </div>
    `;
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('applies values and clicks Load Repo after save', () => {
    const loadButton = Array.from(document.querySelectorAll('button')).find((button) => button.textContent?.includes('Load Repo')) as HTMLButtonElement;
    const onLoad = vi.fn();
    loadButton.addEventListener('click', onLoad);

    installMobileSetupDrawer();
    vi.advanceTimersByTime(901);

    (document.querySelector('[data-field="repoUrl"]') as HTMLInputElement).value = 'https://github.com/owner/repo';
    (document.querySelector('[data-field="accessValue"]') as HTMLInputElement).value = 'value';
    (document.querySelector('[data-action="save"]') as HTMLButtonElement).click();

    vi.advanceTimersByTime(2200);

    expect((document.querySelector('input[aria-label="GitHub Repository URL"]') as HTMLInputElement).value).toBe('https://github.com/owner/repo');
    expect(onLoad).toHaveBeenCalledTimes(1);
  });
});
