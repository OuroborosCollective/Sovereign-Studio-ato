// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type CoachModule = typeof import('./mobile-operator-coach');

const INITIAL_RENDER_DELAY_MS = 700;
const MUTATION_RENDER_DELAY_MS = 120;

function mountShell(extraContent = ''): void {
  document.body.innerHTML = `
    <div id="root">
      <div class="min-h-screen">
        <nav aria-label="Main navigation">
          <button type="button">Repo</button>
          <button type="button">Builder</button>
          <button type="button">Files</button>
          <button type="button">Live Monitor</button>
        </nav>
        <main>${extraContent}</main>
      </div>
    </div>
  `;
}

async function loadCoach(): Promise<CoachModule> {
  vi.resetModules();
  return import('./mobile-operator-coach');
}

function advanceInitialRender(): void {
  vi.advanceTimersByTime(INITIAL_RENDER_DELAY_MS + 1);
}

function advanceMutationRender(): void {
  vi.advanceTimersByTime(MUTATION_RENDER_DELAY_MS + 1);
}

function coachRoot(): HTMLElement {
  const root = document.getElementById('sovereign-mobile-coach');
  expect(root).toBeTruthy();
  return root as HTMLElement;
}

function coachText(): string {
  return coachRoot().textContent ?? '';
}

function dispatchState(detail: unknown): void {
  window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', { detail }));
  advanceMutationRender();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-06-20T08:00:00.000Z'));
  sessionStorage.clear();
  document.body.innerHTML = '';
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  sessionStorage.clear();
  document.body.innerHTML = '';
});

describe('mobile operator coach priority', () => {
  it('keeps runtime state over later dom fallback text', async () => {
    mountShell('idle');
    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    dispatchState({
      lamp: 'red',
      title: 'Runtime Health Stopper',
      message: 'Health gate needs attention.',
      action: 'Open Health.',
      thinking: false,
      source: 'runtime-library',
      tick: 7,
      hash: 'runtime-7',
    });

    expect(coachRoot().className).toBe('red');
    expect(coachText()).toContain('Runtime Health Stopper');

    document.querySelector('main')!.textContent = 'checks passed green gate passed';
    advanceMutationRender();

    expect(coachRoot().className).toBe('red');
    expect(coachText()).toContain('Runtime Health Stopper');
    expect(coachText()).not.toContain('Checks sehen gesund aus');
  });

  it('shows source priority in monitor log', async () => {
    mountShell();
    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    dispatchState({
      lamp: 'green',
      title: 'Runtime Ready',
      message: 'Ready signal.',
      action: 'Continue.',
      thinking: false,
      source: 'runtime-library',
      tick: 9,
    });

    expect(coachText()).toContain('priority:90');
  });
});
