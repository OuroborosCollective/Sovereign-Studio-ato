/**
 * BuilderContainer intent detection tests
 * Tests for executor routing, code-generation intent and Worker diagnostics.
 */

import {
  isSovereignAgentExecutionIntent,
  isCodeGenerationIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
  getWorkerActionHint,
} from '../runtime/workerIntentDetector';

describe('isSovereignAgentExecutionIntent', () => {
  it('detects Sovereign Agent keyword', () => {
    expect(isSovereignAgentExecutionIntent('Use Sovereign Agent to fix this')).toBe(true);
  });

  it('detects draft PR intent', () => {
    expect(isSovereignAgentExecutionIntent('Create a draft PR')).toBe(true);
    expect(isSovereignAgentExecutionIntent('pr erstellen')).toBe(true);
  });

  it('detects push/commit intent', () => {
    expect(isSovereignAgentExecutionIntent('push to main')).toBe(true);
    expect(isSovereignAgentExecutionIntent('commit the changes')).toBe(true);
  });

  it('keeps generic build/implement intent out of Sovereign Agent-only routing', () => {
    expect(isSovereignAgentExecutionIntent('baue die app')).toBe(false);
    expect(isSovereignAgentExecutionIntent('implementiere feature')).toBe(false);
  });

  it('keeps generic fix intent out of Sovereign Agent-only routing', () => {
    expect(isSovereignAgentExecutionIntent('fixe den bug')).toBe(false);
    expect(isSovereignAgentExecutionIntent('repariere den server')).toBe(false);
  });

  it('returns false for non-execution text', () => {
    expect(isSovereignAgentExecutionIntent('Hello world')).toBe(false);
    expect(isSovereignAgentExecutionIntent('What is this project about?')).toBe(false);
  });

  it('is case insensitive', () => {
    expect(isSovereignAgentExecutionIntent('sovereign-agent')).toBe(true);
    expect(isSovereignAgentExecutionIntent('SOVEREIGN_AGENT')).toBe(true);
  });
});

describe('isCodeGenerationIntent', () => {
  it('detects generic code-generation intent without forcing Sovereign Agent', () => {
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
      submittedText: 'Use Sovereign Agent to fix',
      workerBlocked: false,
    })).toBe('Executor-Schreibroute starten');
  });

  it('returns blocked executor hint when agent disabled', () => {
    expect(getWorkerActionHint({
      submittedText: 'sovereign-agent do something',
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
