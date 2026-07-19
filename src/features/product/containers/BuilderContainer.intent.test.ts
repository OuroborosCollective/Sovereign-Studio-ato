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
  it('accepts only explicit executor controls', () => {
    expect(isSovereignAgentExecutionIntent('/agent fix this')).toBe(true);
    expect(isSovereignAgentExecutionIntent('/draft-pr create')).toBe(true);
    expect(isSovereignAgentExecutionIntent('Use Sovereign Agent to fix this')).toBe(false);
    expect(isSovereignAgentExecutionIntent('Create a draft PR')).toBe(false);
    expect(isSovereignAgentExecutionIntent('pr erstellen')).toBe(false);
    expect(isSovereignAgentExecutionIntent('push to main')).toBe(false);
    expect(isSovereignAgentExecutionIntent('commit the changes')).toBe(false);
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

  it('is case insensitive for explicit controls', () => {
    expect(isSovereignAgentExecutionIntent('/AGENT task')).toBe(true);
    expect(isSovereignAgentExecutionIntent('/DRAFT-PR task')).toBe(true);
  });
});

describe('isCodeGenerationIntent', () => {
  it('accepts only explicit code controls', () => {
    expect(isCodeGenerationIntent('/code baue die app')).toBe(true);
    expect(isCodeGenerationIntent('/implement feature')).toBe(true);
    expect(isCodeGenerationIntent('/fix den bug')).toBe(true);
    expect(isCodeGenerationIntent('baue die app')).toBe(false);
    expect(isCodeGenerationIntent('implementiere feature')).toBe(false);
    expect(isCodeGenerationIntent('fixe den bug')).toBe(false);
    expect(isCodeGenerationIntent('repariere den server')).toBe(false);
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

  it('rejects natural-language retry wording', () => {
    expect(isWorkerRetryIntent('/retry')).toBe(true);
    expect(isWorkerRetryIntent('erneut')).toBe(false);
    expect(isWorkerRetryIntent('nochmal')).toBe(false);
    expect(isWorkerRetryIntent('noch mal')).toBe(false);
    expect(isWorkerRetryIntent('wiederholen')).toBe(false);
    expect(isWorkerRetryIntent('testen')).toBe(false);
    expect(isWorkerRetryIntent('versuch es nochmal')).toBe(false);
  });

  it('returns false for unrelated text', () => {
    expect(isWorkerRetryIntent('hello')).toBe(false);
    expect(isWorkerRetryIntent('how are you')).toBe(false);
  });
});

describe('isWorkerDiagnosticQuestion', () => {
  it('accepts only explicit diagnostic controls', () => {
    expect(isWorkerDiagnosticQuestion('diagnose')).toBe(true);
    expect(isWorkerDiagnosticQuestion('/diagnose')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Warum funktioniert das nicht?')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Wieso ist der Worker down?')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Hilfe, der Worker geht nicht')).toBe(false);
    expect(isWorkerDiagnosticQuestion('help me')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Error 500')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Cloudflare worker blocked')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Erkläre mir den Fehler')).toBe(false);
  });

  it('returns false for unrelated text', () => {
    expect(isWorkerDiagnosticQuestion('Hello world')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Build the app')).toBe(false);
  });
});

describe('getWorkerActionHint', () => {
  it('returns executor write-route hint for an explicit executor control', () => {
    expect(getWorkerActionHint({
      submittedText: '/agent fix',
      workerBlocked: false,
    })).toBe('Executor-Schreibroute starten');
  });

  it('returns blocked executor hint when agent disabled', () => {
    expect(getWorkerActionHint({
      submittedText: '/agent do something',
      workerBlocked: true,
      agentDisabled: true,
    })).toBe('Executor blockiert · Code-Route prüft zuerst');
  });

  it('returns code-LLM hint for an explicit code control', () => {
    expect(getWorkerActionHint({
      submittedText: '/code baue die app',
      workerBlocked: false,
    })).toBe('Code-LLM Route · Patch erzeugen');
  });

  it('returns diagnostic hint when worker blocked and no retry intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'Hello world',
      workerBlocked: true,
    })).toBe('Worker blockiert · keine lokale Sprachdeutung');
  });

  it('returns retry hint when worker blocked and retry intent', () => {
    expect(getWorkerActionHint({
      submittedText: 'retry',
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
