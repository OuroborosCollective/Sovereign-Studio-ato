// @vitest-environment jsdom

/**
 * KI Coach Unit Tests
 * Tests the real mobile operator coach runtime/event path and DOM fallback.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type CoachModule = typeof import('./mobile-operator-coach');

type CoachTestWindow = Window &
  typeof globalThis & {
    __sovereignRuntime?: {
      coachState?: unknown;
      mobileCoachState?: unknown;
      operatorCoachState?: unknown;
      state?: unknown;
      snapshot?: unknown;
      telemetry?: unknown;
      metrics?: unknown;
      workflow?: unknown;
      patternMemory?: unknown;
      remoteMemory?: unknown;
      getCoachState?: () => unknown;
      getMobileCoachState?: () => unknown;
      getSnapshot?: () => unknown;
    };
    sovereignRuntime?: CoachTestWindow['__sovereignRuntime'];
    __sovereignCoachState?: unknown;
    __sovereignMobileCoachState?: unknown;
    __sovereignRuntimeCoachState?: unknown;
  };

const INITIAL_RENDER_DELAY_MS = 700;
const MUTATION_RENDER_DELAY_MS = 120;

function testWindow(): CoachTestWindow {
  return window as CoachTestWindow;
}

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

function dispatchCoachState(detail: unknown, eventName = 'sovereign:runtime-coach-state'): void {
  window.dispatchEvent(new CustomEvent(eventName, { detail }));
  advanceMutationRender();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-06-19T08:00:00.000Z'));
  sessionStorage.clear();
  document.body.innerHTML = '';
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  sessionStorage.clear();
  document.body.innerHTML = '';

  const win = testWindow();
  delete win.__sovereignRuntime;
  delete win.sovereignRuntime;
  delete win.__sovereignCoachState;
  delete win.__sovereignMobileCoachState;
  delete win.__sovereignRuntimeCoachState;
});

describe('KI Coach real module', () => {
  it('installs the coach into the app shell', async () => {
    mountShell();

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachRoot()).toBeTruthy();
    expect(coachText()).toContain('Sovereign Bot');
    expect(coachText()).toContain('Ich warte auf den Start');
  });

  it('uses runtime-library state before DOM fallback', async () => {
    mountShell('repo fehlt build failed');

    const { installMobileOperatorCoach, publishMobileOperatorCoachState } = await loadCoach();
    installMobileOperatorCoach();

    publishMobileOperatorCoachState({
      lamp: 'green',
      title: 'Runtime ist Wahrheitspfad',
      message: 'Die Runtime-Library hat den Coach-State direkt geliefert.',
      action: 'Runtime pruefen.',
      thinking: false,
      source: 'runtime-library',
      tick: 100,
      hash: 'runtime-green',
    });

    advanceInitialRender();

    expect(coachRoot().className).toBe('green');
    expect(coachText()).toContain('Runtime ist Wahrheitspfad');
    expect(coachText()).not.toContain('Stopper');
  });

  it('accepts CustomEvent runtime coach state', async () => {
    mountShell();

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    dispatchCoachState({
      lamp: 'green',
      title: 'Workflow angenommen',
      message: 'Telemetry, Pattern Memory und Runtime laufen.',
      action: 'Live Monitor pruefen.',
      thinking: true,
      source: 'workflow',
      tick: 42,
      hash: 'workflow-42',
    });

    expect(coachRoot().className).toBe('green');
    expect(coachText()).toContain('Workflow angenommen');
    expect(coachText()).toContain('matrix-work $');
  });

  it('accepts derived runtime payloads without full coach shape', async () => {
    mountShell();

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    dispatchCoachState(
      {
        status: 'running',
        message: 'Runtime metrics running',
        tick: 12,
        hash: 'metrics-12',
      },
      'sovereign:metrics-state',
    );

    expect(coachRoot().className).toBe('green');
    expect(coachText()).toContain('Runtime arbeitet');
    expect(coachText()).toContain('Runtime metrics running');
  });

  it('reads assigned runtime object state', async () => {
    mountShell();

    testWindow().__sovereignRuntime = {
      coachState: {
        lamp: 'green',
        title: 'Runtime Object aktiv',
        message: 'Der Coach liest die vorhandene Runtime-Library.',
        action: 'Runtime Monitor pruefen.',
        thinking: false,
        source: 'runtime-library',
        tick: 7,
        hash: 'runtime-object-7',
      },
    };

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachRoot().className).toBe('green');
    expect(coachText()).toContain('Runtime Object aktiv');
    expect(coachText()).toContain('runtime $');
  });

  it('detects stalled runtime activity by old updatedAt', async () => {
    mountShell();

    const { installMobileOperatorCoach, publishMobileOperatorCoachState } = await loadCoach();
    installMobileOperatorCoach();

    publishMobileOperatorCoachState({
      lamp: 'green',
      title: 'Runtime arbeitet',
      message: 'Ein alter laufender Zustand ohne frisches Update.',
      action: 'Bitte warten.',
      thinking: true,
      source: 'runtime-library',
      tick: 123,
      hash: 'stale-hash',
      updatedAt: Date.now() - 91_000,
    });

    advanceInitialRender();

    expect(coachRoot().className).toBe('yellow');
    expect(coachText()).toContain('Aktivitaet ohne neues Runtime-Signal');
  });

  it('uses DOM fallback when no runtime state exists', async () => {
    mountShell('runtime validation coverage healthy 21/21 runtime validation');

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachRoot().className).toBe('green');
    expect(coachText()).toContain('Checks sehen gesund aus');
  });

  it('detects real DOM fallback stoppers', async () => {
    mountShell('validation_failed: build failed with error: exit code 1');

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachRoot().className).toBe('red');
    expect(coachText()).toContain('Stopper');
  });

  it('ignores harmless DOM fallback failure counters', async () => {
    mountShell('0 failed, all tests passed, workflow: idle');

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachRoot().className).not.toBe('red');
    expect(coachText()).toContain('Ich warte auf den Start');
  });

  it('does not read its own coach text as source signal', async () => {
    mountShell();

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    document.querySelector('main')!.textContent = '';
    advanceMutationRender();

    expect(coachRoot().className).toBe('yellow');
    expect(coachText()).toContain('Ich warte auf den Start');
  });

  it('updates after DOM mutation without manual reinstall', async () => {
    mountShell('idle');

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachText()).toContain('Ich warte auf den Start');

    document.querySelector('main')!.textContent = 'self review: accepted';
    advanceMutationRender();

    expect(coachRoot().className).toBe('green');
    expect(coachText()).toContain('Ergebnis ist bereit');
  });

  it('coach buttons click external navigation buttons, not coach buttons', async () => {
    mountShell();

    const repoButton = Array.from(document.querySelectorAll('button')).find(
      (button) => button.textContent === 'Repo',
    );

    expect(repoButton).toBeTruthy();

    const onRepoClick = vi.fn();
    repoButton!.addEventListener('click', onRepoClick);

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    const coachRepoButton = coachRoot().querySelector<HTMLButtonElement>('[data-go="Repo"]');
    expect(coachRepoButton).toBeTruthy();

    coachRepoButton!.click();

    expect(onRepoClick).toHaveBeenCalledTimes(1);
  });

  it('persists accepted state in sessionStorage for remount recovery', async () => {
    mountShell();

    let module = await loadCoach();
    module.installMobileOperatorCoach();

    module.publishMobileOperatorCoachState({
      lamp: 'green',
      title: 'Persistierter Runtime-State',
      message: 'Dieser Zustand wird nach Remount wieder geladen.',
      action: 'Monitor pruefen.',
      thinking: false,
      source: 'runtime-library',
      tick: 55,
      hash: 'persisted-55',
    });

    advanceInitialRender();

    expect(coachText()).toContain('Persistierter Runtime-State');

    document.body.innerHTML = '';
    mountShell();

    module = await loadCoach();
    module.installMobileOperatorCoach();
    advanceInitialRender();

    expect(coachText()).toContain('Persistierter Runtime-State');
  });

  it('keeps newer tick over older same-source runtime event', async () => {
    mountShell();

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    dispatchCoachState({
      lamp: 'green',
      title: 'Neuer Runtime Tick',
      message: 'Tick 10 ist gueltig.',
      action: 'Monitor pruefen.',
      thinking: false,
      source: 'workflow',
      tick: 10,
      hash: 'tick-10',
    });

    expect(coachText()).toContain('Neuer Runtime Tick');

    dispatchCoachState({
      lamp: 'green',
      title: 'Alter Runtime Tick',
      message: 'Tick 9 darf den Zustand nicht ueberschreiben.',
      action: 'Nicht anzeigen.',
      thinking: false,
      source: 'workflow',
      tick: 9,
      hash: 'tick-9',
    });

    expect(coachText()).toContain('Neuer Runtime Tick');
    expect(coachText()).not.toContain('Alter Runtime Tick');
  });

  it('allows red runtime state to override previous green state', async () => {
    mountShell();

    const { installMobileOperatorCoach } = await loadCoach();
    installMobileOperatorCoach();
    advanceInitialRender();

    dispatchCoachState({
      lamp: 'green',
      title: 'Runtime gruen',
      message: 'Alles laeuft.',
      action: 'Weiter.',
      thinking: false,
      source: 'runtime-library',
      tick: 1,
      hash: 'green-1',
    });

    expect(coachRoot().className).toBe('green');

    dispatchCoachState({
      lamp: 'red',
      title: 'Runtime Stopper',
      message: 'Die Runtime meldet einen echten Fehler.',
      action: 'Repair pruefen.',
      thinking: false,
      source: 'runtime-library',
      tick: 2,
      hash: 'red-2',
    });

    expect(coachRoot().className).toBe('red');
    expect(coachText()).toContain('Runtime Stopper');
  });
});
