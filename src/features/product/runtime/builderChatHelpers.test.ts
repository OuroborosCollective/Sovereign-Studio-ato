import { describe, expect, it } from 'vitest';
import {
  isWriteIntent,
  isLocalCompletionStatusQuestion,
  buildLocalStatusAnswer,
} from './builderChatHelpers';

describe('isWriteIntent', () => {
  it('detects README/doc change requests', () => {
    expect(isWriteIntent('Bitte README ändern und Titel anpassen')).toBe(true);
    expect(isWriteIntent('Kannst du die Dokumentation anpassen?')).toBe(true);
  });

  it('detects patch/diff/commit/push/PR language', () => {
    expect(isWriteIntent('Erzeuge bitte einen patch')).toBe(true);
    expect(isWriteIntent('zeig mir den diff')).toBe(true);
    expect(isWriteIntent('mach einen commit')).toBe(true);
    expect(isWriteIntent('push das bitte')).toBe(true);
    expect(isWriteIntent('erstelle einen draft pr')).toBe(true);
    expect(isWriteIntent('öffne einen pull request')).toBe(true);
  });

  it('detects separable-verb "passe ... an" pattern', () => {
    expect(isWriteIntent('Kannst du die Datei an das neue Format anpassen')).toBe(false);
    expect(isWriteIntent('Passe die Datei an das neue Format an')).toBe(true);
  });

  it('does not flag plain advisory/chat questions as write intent', () => {
    expect(isWriteIntent('Wie funktioniert React useEffect?')).toBe(false);
    expect(isWriteIntent('Was denkst du über diese Architektur?')).toBe(false);
    expect(isWriteIntent('Erklär mir bitte den Unterschied zwischen let und const')).toBe(false);
  });
});

describe('isLocalCompletionStatusQuestion', () => {
  it('detects completion status questions', () => {
    expect(isLocalCompletionStatusQuestion('Bist du fertig?')).toBe(true);
    expect(isLocalCompletionStatusQuestion('Ist das erledigt?')).toBe(true);
    expect(isLocalCompletionStatusQuestion('Wo ist der patch?')).toBe(true);
    expect(isLocalCompletionStatusQuestion('Gibt es einen Draft PR?')).toBe(true);
  });

  it('does not flag unrelated messages', () => {
    expect(isLocalCompletionStatusQuestion('Baue eine neue Funktion')).toBe(false);
  });
});

describe('buildLocalStatusAnswer', () => {
  const base = {
    githubWriteAllowed: true,
    writeIntentBlockedByRepo: false,
    openhandsRunning: false,
    draftPrUrl: null,
    hasPatch: false,
    hasWorkerResponse: false,
    workerBlocker: null,
  };

  it('reports draft PR ready as the truth', () => {
    expect(buildLocalStatusAnswer({ ...base, draftPrUrl: 'https://github.com/x/y/pull/1' }))
      .toContain('https://github.com/x/y/pull/1');
  });

  it('reports patch generated when no PR yet', () => {
    expect(buildLocalStatusAnswer({ ...base, hasPatch: true })).toMatch(/Patch\/Diff wurde erzeugt/);
  });

  it('reports OpenHands still running', () => {
    expect(buildLocalStatusAnswer({ ...base, openhandsRunning: true })).toMatch(/arbeitet noch/);
  });

  it('reports missing GitHub access honestly instead of claiming done', () => {
    const answer = buildLocalStatusAnswer({ ...base, githubWriteAllowed: false });
    expect(answer).toMatch(/GitHub-Zugang fehlt/);
  });

  it('reports repo-missing block before access-missing', () => {
    const answer = buildLocalStatusAnswer({
      ...base,
      githubWriteAllowed: false,
      writeIntentBlockedByRepo: true,
    });
    expect(answer).toMatch(/GitHub-Repo geladen werden muss/);
  });

  it('never claims done from a mere worker text response', () => {
    const answer = buildLocalStatusAnswer({ ...base, hasWorkerResponse: true });
    expect(answer).toMatch(/nur eine Worker-Antwort/);
    expect(answer.toLowerCase()).not.toMatch(/^ja/);
  });

  it('reports nothing started when runtime is fully idle', () => {
    expect(buildLocalStatusAnswer(base)).toMatch(/kein Auftrag gestartet/);
  });
});
