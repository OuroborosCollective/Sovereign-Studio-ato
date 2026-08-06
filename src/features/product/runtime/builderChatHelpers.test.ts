import { describe, expect, it } from 'vitest';
import {
  isWriteIntent,
  isLocalCompletionStatusQuestion,
  buildLocalStatusAnswer,
} from './builderChatHelpers';

describe('isWriteIntent', () => {
  it('returns the LLM-declared explicit value when provided', () => {
    // The LLM (Brain) classifies intent; the runtime just passes it through.
    expect(isWriteIntent('Bitte README ändern', true)).toBe(true);
    expect(isWriteIntent('Wie funktioniert React?', false)).toBe(false);
    expect(isWriteIntent('erstelle einen draft pr', true)).toBe(true);
  });

  it('returns false when no explicit classification is provided — LLM must declare intent', () => {
    // Keyword-based pre-classification has been removed. Without LLM input, default is false.
    expect(isWriteIntent('Bitte README ändern und Titel anpassen')).toBe(false);
    expect(isWriteIntent('Erzeuge bitte einen patch')).toBe(false);
    expect(isWriteIntent('mach einen commit')).toBe(false);
    expect(isWriteIntent('erstelle einen draft pr')).toBe(false);
    expect(isWriteIntent('Passe die Datei an das neue Format an')).toBe(false);
  });

  it('returns false for advisory/chat questions regardless of content', () => {
    expect(isWriteIntent('Wie funktioniert React useEffect?')).toBe(false);
    expect(isWriteIntent('Was denkst du über diese Architektur?')).toBe(false);
  });
});

describe('isLocalCompletionStatusQuestion', () => {
  it('returns the LLM-declared explicit value when provided', () => {
    expect(isLocalCompletionStatusQuestion('Bist du fertig?', true)).toBe(true);
    expect(isLocalCompletionStatusQuestion('Baue eine neue Funktion', false)).toBe(false);
  });

  it('returns false when no explicit classification is provided — LLM must declare intent', () => {
    // Keyword-based pre-classification has been removed. Without LLM input, default is false.
    expect(isLocalCompletionStatusQuestion('Bist du fertig?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Ist das erledigt?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Wo ist der patch?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Gibt es einen Draft PR?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Baue eine neue Funktion')).toBe(false);
  });
});

describe('buildLocalStatusAnswer', () => {
  const base = {
    githubWriteAllowed: true,
    writeIntentBlockedByRepo: false,
    agentRunning: false,
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

  it('reports Sovereign Agent still running', () => {
    expect(buildLocalStatusAnswer({ ...base, agentRunning: true })).toMatch(/Sovereign Agent arbeitet noch/);
  });

  it('reports missing GitHub access honestly instead of claiming done', () => {
    const answer = buildLocalStatusAnswer({ ...base, githubWriteAllowed: false });
    expect(answer).toMatch(/GitHub-Zugang fehlt/);
  });

  it('reports GitHub access validation in progress instead of claiming missing or done', () => {
    const answer = buildLocalStatusAnswer({
      ...base,
      githubWriteAllowed: false,
      githubAccessState: 'validating',
    });

    expect(answer).toMatch(/GitHub-Zugang wird gerade geprüft/);
    expect(answer.toLowerCase()).not.toMatch(/^ja/);
  });

  it('reports format-only GitHub access as not API-validated yet', () => {
    const answer = buildLocalStatusAnswer({
      ...base,
      githubWriteAllowed: false,
      githubAccessState: 'requested',
    });

    expect(answer).toMatch(/echte GitHub-API-Prüfung steht noch aus/);
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
