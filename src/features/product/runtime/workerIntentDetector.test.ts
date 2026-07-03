/**
 * workerIntentDetector tests
 * Unit tests for Worker intent detection functions
 */

import {
  isOpenHandsExecutionIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
  isDelegationIntent,
  hasCodeContextInHistory,
  isDelegatedOpenHandsExecutionIntent,
  getWorkerActionHint,
} from './workerIntentDetector';

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

describe('isDelegationIntent', () => {
  it('detects "Tu du das für mich"', () => {
    expect(isDelegationIntent('Tu du das für mich')).toBe(true);
    expect(isDelegationIntent('tu du das')).toBe(true);
  });

  it('detects "Mach das für mich"', () => {
    expect(isDelegationIntent('Mach das für mich')).toBe(true);
    expect(isDelegationIntent('mach das')).toBe(true);
  });

  it('detects "Erledige das"', () => {
    expect(isDelegationIntent('Erledige das bitte')).toBe(true);
  });

  it('detects "Übernimm das"', () => {
    expect(isDelegationIntent('Übernimm das für mich')).toBe(true);
  });

  it('detects "Kannst du das für mich"', () => {
    expect(isDelegationIntent('Kannst du das für mich machen?')).toBe(true);
  });

  it('is case insensitive', () => {
    expect(isDelegationIntent('TU DU DAS')).toBe(true);
    expect(isDelegationIntent('Mach Das Für Mich')).toBe(true);
  });

  it('returns false for unrelated text', () => {
    expect(isDelegationIntent('Wie geht es dir?')).toBe(false);
    expect(isDelegationIntent('Was ist Sovereign Studio?')).toBe(false);
  });
});

describe('hasCodeContextInHistory', () => {
  it('returns true when history contains README', () => {
    const history = [
      { role: 'user', text: 'Aktualisiere das README' },
      { role: 'assistant', text: 'Ich werde das README aktualisieren.' },
    ];
    expect(hasCodeContextInHistory(history)).toBe(true);
  });

  it('returns true when history contains code keywords', () => {
    const history = [
      { role: 'user', text: 'Schreibe einen Fix für den Bug' },
      { role: 'assistant', text: 'Hier ist der Fix.' },
    ];
    expect(hasCodeContextInHistory(history)).toBe(true);
  });

  it('returns true when history contains PR/commit keywords', () => {
    const history = [
      { role: 'user', text: 'Erstelle einen Draft PR' },
      { role: 'assistant', text: 'Draft PR wird erstellt.' },
    ];
    expect(hasCodeContextInHistory(history)).toBe(true);
  });

  it('returns false for casual chat without code context', () => {
    const history = [
      { role: 'user', text: 'Hallo, wie geht es dir?' },
      { role: 'assistant', text: 'Mir geht es gut, danke!' },
    ];
    expect(hasCodeContextInHistory(history)).toBe(false);
  });

  it('returns false for empty history', () => {
    expect(hasCodeContextInHistory([])).toBe(false);
  });

  it('considers only last 6 messages', () => {
    const history = [
      { role: 'user', text: 'Alte Nachricht' },
      { role: 'assistant', text: 'Alte Antwort' },
      { role: 'user', text: 'Wie ist das Wetter?' },
      { role: 'assistant', text: 'Sonnig!' },
      { role: 'user', text: 'Schreibe einen Test für die Datei utils.ts' },
      { role: 'assistant', text: 'Test geschrieben.' },
      { role: 'user', text: 'Tu du das für mich' },
    ];
    expect(hasCodeContextInHistory(history)).toBe(true);
  });
});

describe('isDelegatedOpenHandsExecutionIntent', () => {
  it('returns true when delegation after README task', () => {
    const history = [
      { role: 'user', text: 'Aktualisiere das README' },
      { role: 'assistant', text: 'Bereite die Aktualisierung vor.' },
      { role: 'user', text: 'Tu du das für mich' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Tu du das für mich', history)).toBe(true);
  });

  it('returns true when delegation after code change task', () => {
    const history = [
      { role: 'user', text: 'Füge einen Test hinzu' },
      { role: 'assistant', text: 'Ich schlage einen Test vor.' },
      { role: 'user', text: 'Mach das' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Mach das', history)).toBe(true);
  });

  it('returns false when delegation without code context', () => {
    const history = [
      { role: 'user', text: 'Hallo' },
      { role: 'assistant', text: 'Hallo!' },
      { role: 'user', text: 'Tu du das für mich' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Tu du das für mich', history)).toBe(false);
  });

  it('returns false for non-delegation text even with code context', () => {
    const history = [
      { role: 'user', text: 'Aktualisiere die Datei' },
      { role: 'assistant', text: 'Welche Datei?' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Welche Datei meinst du?', history)).toBe(false);
  });

  it('returns false for delegation request after pure chat question', () => {
    const history = [
      { role: 'user', text: 'Was ist Sovereign Studio?' },
      { role: 'assistant', text: 'Es ist ein Tool.' },
      { role: 'user', text: 'Mach das für mich' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Mach das für mich', history)).toBe(false);
  });
});

describe('getWorkerActionHint', () => {
  it('returns OpenHands hint for execution intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'Use OpenHands to fix',
      workerBlocked: false,
    })).toBe('OpenHands Executor starten');
  });

  it('returns blocked + OpenHands hint when agent disabled', () => {
    expect(getWorkerActionHint({
      submittedText: 'openhands do something',
      workerBlocked: true,
      agentDisabled: true,
    })).toBe('OpenHands blockiert · Worker erklärt zuerst');
  });

  it('returns diagnostic hint when worker blocked and no retry intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'Hello world',
      workerBlocked: true,
    })).toBe('Worker blockiert · lokale Diagnose statt blindem Retry');
  });

  it('returns retry hint when worker blocked and retry intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'retry the request',
      workerBlocked: true,
    })).toBe('Worker Retry · Diagnose wird aktualisiert');
  });

  it('returns empty string when no worker blocked and no special intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'What is this project?',
      workerBlocked: false,
    })).toBe('');
  });
});
