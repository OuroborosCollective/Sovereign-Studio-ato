// @vitest-environment jsdom

import { afterEach, describe, expect, it } from 'vitest';
import type { SovereignDependencyCoachSignal } from './sovereignDependencyCoachBridge';
import {
  readSovereignDependencySignals,
  resetSovereignDependencyBrowserSurfaceForTests,
  upsertSovereignDependencySignal,
  writeSovereignDependencySignals,
} from './sovereignDependencyBrowserSurface';

function signal(key: string): SovereignDependencyCoachSignal {
  return {
    lamp: 'green',
    title: key,
    message: key,
    action: 'Continue.',
    thinking: false,
    source: 'github',
    dependencyKey: key,
    dependencyPhase: 'ready',
    telemetryLevel: 'success',
    telemetryLabel: 'dependency:github:ready',
    telemetryMessage: key,
  };
}

afterEach(() => {
  resetSovereignDependencyBrowserSurfaceForTests();
  document.body.innerHTML = '';
  window.sessionStorage.clear();
});

describe('sovereignDependencyBrowserSurface', () => {
  it('stores and reads dependency signals', () => {
    writeSovereignDependencySignals([signal('repo'), signal('workflow')]);
    expect(readSovereignDependencySignals().map((item) => item.dependencyKey)).toEqual(['repo', 'workflow']);
  });

  it('replaces existing dependency keys', () => {
    upsertSovereignDependencySignal(signal('repo'));
    upsertSovereignDependencySignal({ ...signal('repo'), title: 'updated' });
    expect(readSovereignDependencySignals()).toHaveLength(1);
    expect(readSovereignDependencySignals()[0].title).toBe('updated');
  });
});
