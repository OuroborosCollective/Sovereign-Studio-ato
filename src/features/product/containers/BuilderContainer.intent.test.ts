/**
 * BuilderContainer intent detection tests
 * Tests for executor routing, code-generation intent and Worker diagnostics.
 */

import {
  isOpenHandsExecutionIntent,
  isCodeGenerationIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
  getWorkerActionHint,
} from '../runtime/workerIntentDetector';

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

  it('keeps generic build/implement intent out of OpenHands-only routing', () => {
    expect(isOpenHandsExecutionIntent('baue die app')).toBe(false);
    expect(isOpenHandsExecutionIntent('implementiere feature')).toBe(false);
  });

  it('keeps generic fix intent out of OpenHands-only routing', () => {
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
  it('detects generic code-generation intent without forcing OpenHands', () => {
    expect(isCodeGenerationIntent('baue die app')).toBe(true);
    expect(isCodeGenerationIntent('implementiere feature')).toBe(true);
    expect(isCodeGenerationIntent('fixe den bug')).toBe(true);
    expect(isCodeGenerationIntent('repariere den server')).toBe(true);
  });

  it('does not treat ordinary chat as code-generation intent', () => {
    expect(isCodeGenerationIntent('Hello world')).toBe(false);
    expect(isCodeGenerationIntent('Was ist dieses Projekt?')).toBe(false);
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

describe('getWorkerActionHint', () => {
  it('returns executor write-route hint for explicit executor intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'Use OpenHands to fix',
      workerBlocked: false,
    })).toBe('Executor-Schreibroute starten');
  });

  it('returns blocked executor hint when agent disabled', () => {
    expect(getWorkerActionHint({
      submittedText: 'openhands do something',
      workerBlocked: true,
      agentDisabled: true,
    })).toBe('Executor blockiert · Code-Route prüft zuerst');
  });

  it('returns code-LLM hint for generic code-generation intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'baue die app',
      workerBlocked: false,
    })).toBe('Code-LLM Route · Patch erzeugen');
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
