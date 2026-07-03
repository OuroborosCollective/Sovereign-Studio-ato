/**
 * workerIntentDetector tests
 * Unit tests for Worker intent detection functions
 */

import {
  isOpenHandsExecutionIntent,
  isCodeGenerationIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
  isDelegationIntent,
  hasCodeContextInHistory,
  isDelegatedOpenHandsExecutionIntent,
  getWorkerActionHint,
  isExecutorStatusQuestion,
  buildExecutorStatusAnswer,
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

  it('does not treat generic build/implement intent as OpenHands-only execution', () => {
    expect(isOpenHandsExecutionIntent('baue die app')).toBe(false);
    expect(isOpenHandsExecutionIntent('implementiere feature')).toBe(false);
  });

  it('does not treat generic fix intent as OpenHands-only execution', () => {
    expect(isOpenHandsExecutionIntent('fixe den bug')).toBe(false);
    expect(isOpenHandsExecutionIntent('repariere den server')).toBe(false);
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

describe('isCodeGenerationIntent', () => {
  it('detects generic code work for code-capable LLM routes', () => {
    expect(isCodeGenerationIntent('baue die app')).toBe(true);
    expect(isCodeGenerationIntent('implementiere feature')).toBe(true);
    expect(isCodeGenerationIntent('fixe den bug')).toBe(true);
    expect(isCodeGenerationIntent('repariere den server')).toBe(true);
  });

  it('does not classify normal chat as code generation', () => {
    expect(isCodeGenerationIntent('Was ist Sovereign Studio?')).toBe(false);
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
  it('returns false when delegation follows only generic code generation context', () => {
    const history = [
      { role: 'user', text: 'Aktualisiere das README' },
      { role: 'assistant', text: 'Bereite einen Patchvorschlag vor.' },
      { role: 'user', text: 'Tu du das für mich' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Tu du das für mich', history)).toBe(false);
  });

  it('returns true when delegation follows explicit Draft PR executor context', () => {
    const history = [
      { role: 'user', text: 'Erstelle einen Draft PR mit einem Test.' },
      { role: 'assistant', text: 'Draft PR benötigt eine Schreibroute.' },
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

describe('isDelegationIntent — Phase 1 spec cases', () => {
  it('"Tu du das für mich" after README task is delegation intent', () => {
    expect(isDelegationIntent('Tu du das für mich')).toBe(true);
  });

  it('"Mach das" is delegation intent', () => {
    expect(isDelegationIntent('Mach das')).toBe(true);
  });

  it('"Setz das um" is delegation intent (short form)', () => {
    expect(isDelegationIntent('Setz das um')).toBe(true);
  });

  it('"Setze das um" is delegation intent (long form)', () => {
    expect(isDelegationIntent('Setze das um')).toBe(true);
  });

  it('"Was ist Sovereign?" is not delegation intent', () => {
    expect(isDelegationIntent('Was ist Sovereign?')).toBe(false);
  });
});

describe('isDelegatedOpenHandsExecutionIntent — Phase 1 spec cases', () => {
  it('returns false: "Tu du das für mich" after README-Auftrag without explicit executor context', () => {
    const history = [
      { role: 'assistant', text: 'Ich ändere das README und füge einen Titel ein.' },
      { role: 'user', text: 'Tu du das für mich' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Tu du das für mich', history)).toBe(false);
  });

  it('returns false: "Tu du das für mich" after normal chat question (no code context)', () => {
    const history = [
      { role: 'user', text: 'Was ist dein Name?' },
      { role: 'assistant', text: 'Ich bin Sovereign.' },
      { role: 'user', text: 'Tu du das für mich' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Tu du das für mich', history)).toBe(false);
  });
});

describe('isExecutorStatusQuestion', () => {
  it('detects "arbeitet er schon?"', () => {
    expect(isExecutorStatusQuestion('arbeitet er schon?')).toBe(true);
  });

  it('detects "läuft das?"', () => {
    expect(isExecutorStatusQuestion('läuft das?')).toBe(true);
  });

  it('detects "was macht er?"', () => {
    expect(isExecutorStatusQuestion('was macht er?')).toBe(true);
  });

  it('detects "ist er fertig?"', () => {
    expect(isExecutorStatusQuestion('ist er fertig?')).toBe(true);
  });

  it('detects "hat er angefangen?"', () => {
    expect(isExecutorStatusQuestion('hat er angefangen?')).toBe(true);
  });

  it('detects "warum passiert nichts?"', () => {
    expect(isExecutorStatusQuestion('warum passiert nichts?')).toBe(true);
  });

  it('detects "sehe nichts bei replit"', () => {
    expect(isExecutorStatusQuestion('sehe nichts bei replit')).toBe(true);
  });

  it('is case insensitive', () => {
    expect(isExecutorStatusQuestion('ARBEITET ER SCHON?')).toBe(true);
    expect(isExecutorStatusQuestion('Läuft Das?')).toBe(true);
  });

  it('returns false for unrelated messages', () => {
    expect(isExecutorStatusQuestion('Baue mir ein Feature')).toBe(false);
    expect(isExecutorStatusQuestion('Was ist das Sovereign Studio?')).toBe(false);
    expect(isExecutorStatusQuestion('Implementiere den Fix')).toBe(false);
  });

  it('returns false for generic "Warum?" diagnostic questions (no executor status token)', () => {
    // "Warum?" alone is a diagnostic question, not an executor status question.
    // It should go through the workerDiagnosticQuestion route, not executor status.
    expect(isExecutorStatusQuestion('Warum?')).toBe(false);
    expect(isExecutorStatusQuestion('Wieso?')).toBe(false);
  });
});

describe('buildExecutorStatusAnswer', () => {
  it('reports idle honestly when no executor is running', () => {
    const answer = buildExecutorStatusAnswer({ agentState: 'idle' });
    expect(answer).toContain('Nein');
    expect(answer).toContain('gestartet');
  });

  it('reports running with file count and draft PR status', () => {
    const answer = buildExecutorStatusAnswer({
      agentState: 'executor_running',
      openhandsStatus: 'running',
      changedFiles: 2,
      draftPrUrl: null,
    });
    expect(answer).toContain('Ja');
    expect(answer).toContain('2');
    expect(answer).toContain('Draft PR');
  });

  it('reports blocked with reason', () => {
    const answer = buildExecutorStatusAnswer({
      agentState: 'blocked',
      blockerReason: 'GitHub-Schreibzugang fehlt.',
    });
    expect(answer).toContain('blockiert');
    expect(answer).toContain('GitHub-Schreibzugang fehlt');
  });

  it('reports draft PR ready with URL', () => {
    const answer = buildExecutorStatusAnswer({
      agentState: 'draft_pr_ready',
      draftPrUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/42',
    });
    expect(answer).toContain('https://github.com');
  });

  it('never fabricates: empty idle state is explicit, not "arbeitet"', () => {
    const answer = buildExecutorStatusAnswer({ agentState: 'idle', openhandsStatus: 'idle' });
    expect(answer.toLowerCase()).not.toContain('ja, openhands läuft');
  });
});

describe('getWorkerActionHint', () => {
  it('returns executor hint for explicit execution intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'Use OpenHands to fix',
      workerBlocked: false,
    })).toBe('Executor-Schreibroute starten');
  });

  it('returns code LLM hint for generic code generation intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'implementiere den Fix',
      workerBlocked: false,
    })).toBe('Code-LLM Route · Patch erzeugen');
  });

  it('returns blocked executor hint when agent disabled', () => {
    expect(getWorkerActionHint({
      submittedText: 'openhands do something',
      workerBlocked: true,
      agentDisabled: true,
    })).toBe('Executor blockiert · Code-Route prüft zuerst');
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
