/**
 * KI Coach Unit Tests
 * Tests the mobile operator coach logic
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock coach state detection functions
type CoachLamp = 'green' | 'yellow' | 'red';

interface CoachState {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
}

function hasAny(source: string, tokens: string[]): boolean {
  const lower = source.toLowerCase();
  return tokens.some((token) => lower.includes(token.toLowerCase()));
}

function hasRealStopper(source: string): boolean {
  const lower = source.toLowerCase();
  const harmless = [
    '0 failed',
    'no active step; 0 completed step(s), 0 failed step(s)',
    'repair oder monitor pruefen',
    'repair or monitor',
    'repair plan idle',
    'workflow: idle',
  ];
  if (harmless.some((token) => lower.includes(token))) return false;
  return [
    'validation_failed',
    'draft pr failed',
    'build failed',
    'workflow failed',
    'critical blocker',
    'fehlgeschlagen',
    'blockierender fehler',
    'error:',
  ].some((token) => lower.includes(token));
}

function readCoachState(pageContent: string): CoachState {
  const thinking = hasAny(pageContent, ['läuft', 'running', 'busy', 'in progress', 'is building', 'is watching', 'draft pr läuft']);

  if (hasRealStopper(pageContent)) {
    return { lamp: 'red', title: 'Ich sehe einen echten Stopper', message: 'Ich zeige dir jetzt Repair oder Logs.', action: 'Repair/Logs automatisch pruefen.', thinking: false };
  }

  if (thinking) {
    return { lamp: 'green', title: 'Ich arbeite gerade', message: 'Ich analysiere und pruefe.', action: 'Bitte warten.', thinking: true };
  }

  if (hasAny(pageContent, ['self review: accepted', 'generated-output-accepted', 'generated package passed self review'])) {
    return { lamp: 'green', title: 'Ergebnis ist bereit', message: 'Die Dateien sind akzeptiert.', action: 'Files/Diff pruefen.', thinking: false };
  }

  if (hasAny(pageContent, ['repo fehlt', 'repo snapshot required', 'repository snapshot is not ready', 'noch kein echtes repo', 'automation needs a loaded repository snapshot'])) {
    return { lamp: 'yellow', title: 'Ich brauche zuerst dein Repo', message: 'Oeffne das Zahnrad oder tippe Repo.', action: 'Repo Setup oeffnen.', thinking: false };
  }

  if (hasAny(pageContent, ['pre-publish review', 'generated file']) && !hasAny(pageContent, ['self review'])) {
    return { lamp: 'green', title: 'Ich habe Ergebnis-Dateien', message: 'Pruefe kurz die erzeugten Dateien.', action: 'Dateien pruefen.', thinking: false };
  }

  if (hasAny(pageContent, ['runtime validation coverage', 'healthy', '21/21 runtime validation'])) {
    return { lamp: 'green', title: 'Checks sehen gesund aus', message: 'Die Runtime-Pruefung ist gruen.', action: 'Weiter im Hauptfluss.', thinking: false };
  }

  if (hasAny(pageContent, ['platzhalter', 'konkreten auftrag', 'concrete mission'])) {
    return { lamp: 'yellow', title: 'Ich brauche deinen Wunsch', message: 'Schreibe kurz, was ich verbessern soll.', action: 'Auftrag schreiben.', thinking: false };
  }

  return { lamp: 'yellow', title: 'Ich warte auf den Start', message: 'Beginne mit Repo Setup.', action: 'Repo oeffnen.', thinking: false };
}

describe('KI Coach Logic', () => {
  describe('hasRealStopper', () => {
    it('detects validation_failed error', () => {
      expect(hasRealStopper('validation_failed: something went wrong')).toBe(true);
    });

    it('detects draft pr failed', () => {
      expect(hasRealStopper('draft pr failed to create')).toBe(true);
    });

    it('detects build failed', () => {
      expect(hasRealStopper('build failed with exit code 1')).toBe(true);
    });

    it('detects workflow failed', () => {
      expect(hasRealStopper('workflow failed on ci check')).toBe(true);
    });

    it('detects critical blocker', () => {
      expect(hasRealStopper('critical blocker detected')).toBe(true);
    });

    it('detects German error messages', () => {
      expect(hasRealStopper('fehlgeschlagen bei der validierung')).toBe(true);
      expect(hasRealStopper('blockierender fehler im workflow')).toBe(true);
    });

    it('detects generic error:', () => {
      expect(hasRealStopper('error: connection timeout')).toBe(true);
    });

    it('ignores harmless messages with 0 failed', () => {
      expect(hasRealStopper('0 failed, all tests passed')).toBe(false);
    });

    it('ignores repair plan idle', () => {
      expect(hasRealStopper('repair plan idle')).toBe(false);
    });

    it('ignores workflow: idle', () => {
      expect(hasRealStopper('workflow: idle')).toBe(false);
    });

    it('ignores repair oder monitor pruefen', () => {
      expect(hasRealStopper('repair oder monitor pruefen')).toBe(false);
    });
  });

  describe('readCoachState', () => {
    it('returns RED when real stopper detected', () => {
      const state = readCoachState('validation_failed: something went wrong');
      expect(state.lamp).toBe('red');
      expect(state.title).toContain('Stopper');
    });

    it('returns GREEN when thinking/running', () => {
      const state = readCoachState('is building, please wait');
      expect(state.lamp).toBe('green');
      expect(state.thinking).toBe(true);
    });

    it('returns GREEN when self review accepted', () => {
      const state = readCoachState('self review: accepted');
      expect(state.lamp).toBe('green');
      expect(state.title).toContain('Ergebnis');
    });

    it('returns YELLOW when repo missing', () => {
      const state = readCoachState('repo fehlt, bitte laden');
      expect(state.lamp).toBe('yellow');
      expect(state.title).toContain('Repo');
    });

    it('returns GREEN when files generated', () => {
      const state = readCoachState('pre-publish review generated file ready');
      expect(state.lamp).toBe('green');
    });

    it('returns GREEN when validation healthy', () => {
      const state = readCoachState('runtime validation coverage healthy 21/21');
      expect(state.lamp).toBe('green');
      expect(state.title).toContain('gesund');
    });

    it('returns YELLOW when mission missing', () => {
      const state = readCoachState('platzhalter auftrag, concrete mission required');
      expect(state.lamp).toBe('yellow');
      expect(state.title).toContain('Wunsch');
    });

    it('returns YELLOW by default when waiting for start', () => {
      const state = readCoachState('idle, waiting for input');
      expect(state.lamp).toBe('yellow');
      expect(state.title).toContain('warte');
    });
  });

  describe('hasAny', () => {
    it('matches tokens case-insensitively', () => {
      expect(hasAny('HELLO WORLD', ['hello'])).toBe(true);
      expect(hasAny('hello world', ['HELLO'])).toBe(true);
    });

    it('returns false when no match', () => {
      expect(hasAny('hello world', ['goodbye'])).toBe(false);
    });

    it('matches multiple tokens', () => {
      expect(hasAny('running busy', ['running', 'busy'])).toBe(true);
      expect(hasAny('running', ['running', 'busy'])).toBe(true);
    });
  });

  describe('Coach Status Transitions', () => {
    it('follows happy path: waiting -> thinking -> green', () => {
      // Initial state: waiting for repo
      let state = readCoachState('idle');
      expect(state.lamp).toBe('yellow');

      // After repo loaded: thinking
      state = readCoachState('running, is building');
      expect(state.lamp).toBe('green');
      expect(state.thinking).toBe(true);

      // After completion: green ready
      state = readCoachState('self review: accepted, files ready');
      expect(state.lamp).toBe('green');
      expect(state.thinking).toBe(false);
    });

    it('detects error state at any point', () => {
      // In the middle of workflow
      const state = readCoachState('running, build failed with error');
      expect(state.lamp).toBe('red');
    });

    it('recovers from warning states', () => {
      // Mission missing
      let state = readCoachState('platzhalter');
      expect(state.lamp).toBe('yellow');

      // Mission provided
      state = readCoachState('running, concrete mission loaded');
      expect(state.lamp).toBe('green');
    });
  });
});
