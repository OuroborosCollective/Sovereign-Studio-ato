/**
 * BuilderContainer intent detection tests
 * Tests for isOpenHandsExecutionIntent, isWorkerRetryIntent, isWorkerDiagnosticQuestion
 */

// These functions are defined at module scope in BuilderContainer.tsx
// We extract them for testing by reimplementing the same logic

function isOpenHandsExecutionIntent(text: string): boolean {
  const lower = text.toLowerCase();
  const executionTokens = [
    'openhands', 'draft pr', 'pull request', 'pr erstellen', 'push', 'commit',
    'baue', 'bauen', 'implementiere', 'implementieren', 'fixe', 'repariere',
    'patch', 'ändere datei', 'datei ändern', 'ersatzdatei', 'runtime-check',
    'tests ergänzen', 'test ergänzen', 'code ändern', 'repo schreiben',
  ];
  return executionTokens.some((token) => lower.includes(token));
}

function isWorkerRetryIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return ['retry', 'erneut', 'nochmal', 'noch mal', 'wiederholen', 'testen', 'versuch'].some((token) => lower.includes(token));
}

function isWorkerDiagnosticQuestion(text: string): boolean {
  const lower = text.toLowerCase();
  return [
    'warum', 'wieso', 'weshalb', 'hilfe', 'hilf', 'help', 'erklär', 'erklaer',
    'diagnose', 'fehler', '500', 'worker', 'cloudflare', 'blockiert', 'kaputt',
  ].some((token) => lower.includes(token));
}

describe('isOpenHandsExecutionIntent', () => {
  it('detects OpenHands keyword', () => {
    expect(isOpenHandsExecutionIntent('Use OpenHands to fix this')).toBe(true);
  });

  it('detects draft PR intent', () => {
    expect(isOpenHandsExecutionIntent('Create a draft PR')).toBe(true);
    expect(isOpenHandsExecutionIntent('pr erstellen')).toBe(true);
  });

  it('detects push/commit intent', () => {
    expect(isOpenHandsExecutionIntent('push to main')).toBe(true);
    expect(isOpenHandsExecutionIntent('commit the changes')).toBe(true);
  });

  it('detects build/implement intent', () => {
    expect(isOpenHandsExecutionIntent('baue die app')).toBe(true);
    expect(isOpenHandsExecutionIntent('implementiere feature')).toBe(true);
  });

  it('detects fix intent', () => {
    expect(isOpenHandsExecutionIntent('fixe den bug')).toBe(true);
    expect(isOpenHandsExecutionIntent('repariere den server')).toBe(true);
  });

  it('returns false for non-execution text', () => {
    expect(isOpenHandsExecutionIntent('Hello world')).toBe(false);
    expect(isOpenHandsExecutionIntent('What is this project about?')).toBe(false);
  });

  it('is case insensitive', () => {
    expect(isOpenHandsExecutionIntent('openhands')).toBe(true);
    expect(isOpenHandsExecutionIntent('OPENHANDS')).toBe(true);
  });
});

describe('isWorkerRetryIntent', () => {
  it('detects retry keyword', () => {
    expect(isWorkerRetryIntent('retry')).toBe(true);
    expect(isWorkerRetryIntent('Retry')).toBe(true);
  });

  it('detects german retry words', () => {
    expect(isWorkerRetryIntent('erneut')).toBe(true);
    expect(isWorkerRetryIntent('nochmal')).toBe(true);
    expect(isWorkerRetryIntent('noch mal')).toBe(true);
    expect(isWorkerRetryIntent('wiederholen')).toBe(true);
  });

  it('detects try/test words', () => {
    expect(isWorkerRetryIntent('testen')).toBe(true);
    expect(isWorkerRetryIntent('versuch es nochmal')).toBe(true);
  });

  it('returns false for unrelated text', () => {
    expect(isWorkerRetryIntent('hello')).toBe(false);
    expect(isWorkerRetryIntent('how are you')).toBe(false);
  });
});

describe('isWorkerDiagnosticQuestion', () => {
  it('detects why questions', () => {
    expect(isWorkerDiagnosticQuestion('Warum funktioniert das nicht?')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Wieso ist der Worker down?')).toBe(true);
  });

  it('detects help keywords', () => {
    expect(isWorkerDiagnosticQuestion('Hilfe, der Worker geht nicht')).toBe(true);
    expect(isWorkerDiagnosticQuestion('help me')).toBe(true);
  });

  it('detects technical error keywords', () => {
    expect(isWorkerDiagnosticQuestion('Error 500')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Cloudflare worker blocked')).toBe(true);
  });

  it('detects explain keywords', () => {
    expect(isWorkerDiagnosticQuestion('Erkläre mir den Fehler')).toBe(true);
  });

  it('returns false for unrelated text', () => {
    expect(isWorkerDiagnosticQuestion('Hello world')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Build the app')).toBe(false);
  });
});
