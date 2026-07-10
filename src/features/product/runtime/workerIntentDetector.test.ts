import { describe, expect, it } from 'vitest';
import {
  buildExecutorStatusAnswer,
  getWorkerActionHint,
  hasCodeContextInHistory,
  isCodeGenerationIntent,
  isDelegatedSovereignAgentExecutionIntent,
  isDelegationIntent,
  isExecutorStatusQuestion,
  isLikelyIntegrationImplementationIntent,
  isSovereignAgentExecutionIntent,
  isWorkerDiagnosticQuestion,
  isWorkerRetryIntent,
} from './workerIntentDetector';

describe('integration intent default', () => {
  it('treats normal non-question text as implementation intent without forcing executor-only routing', () => {
    const text = 'Die Oberflaeche soll ruhiger und eindeutiger werden';
    expect(isLikelyIntegrationImplementationIntent(text)).toBe(true);
    expect(isSovereignAgentExecutionIntent(text)).toBe(false);
    expect(isCodeGenerationIntent(text)).toBe(true);
  });

  it('keeps questions advisory instead of auto-executing', () => {
    const text = 'Wie sollte die Oberflaeche besser werden?';
    expect(isLikelyIntegrationImplementationIntent(text)).toBe(false);
    expect(isSovereignAgentExecutionIntent(text)).toBe(false);
    expect(isCodeGenerationIntent(text)).toBe(false);
  });

  it('keeps commands, greetings, retry and alternate route text out of default execution', () => {
    expect(isLikelyIntegrationImplementationIntent('/repo owner/name')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('Hallo')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('retry')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('ohne Sovereign Agent bitte')).toBe(false);
  });
});

describe('explicit executor intent', () => {
  it('detects explicit executor and PR wording only', () => {
    expect(isSovereignAgentExecutionIntent('Use Sovereign Agent to fix this')).toBe(true);
    expect(isSovereignAgentExecutionIntent('Create a draft PR')).toBe(true);
    expect(isSovereignAgentExecutionIntent('push to main')).toBe(true);
    expect(isSovereignAgentExecutionIntent('commit the changes')).toBe(true);
  });

  it('keeps generic build and fix text in code route', () => {
    expect(isSovereignAgentExecutionIntent('baue die app')).toBe(false);
    expect(isSovereignAgentExecutionIntent('implementiere feature')).toBe(false);
    expect(isSovereignAgentExecutionIntent('fixe den bug')).toBe(false);
    expect(isCodeGenerationIntent('baue die app')).toBe(true);
  });
});

describe('retry, diagnostics and status', () => {
  it('detects retry and diagnostic wording', () => {
    expect(isWorkerRetryIntent('retry')).toBe(true);
    expect(isWorkerRetryIntent('nochmal')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Warum funktioniert das nicht?')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Error 500')).toBe(true);
  });

  it('detects executor status questions and reports runtime state honestly', () => {
    expect(isExecutorStatusQuestion('arbeitet er schon?')).toBe(true);
    expect(isExecutorStatusQuestion('warum passiert nichts?')).toBe(true);
    expect(buildExecutorStatusAnswer({ agentState: 'idle' })).toContain('nicht');
    expect(buildExecutorStatusAnswer({ agentState: 'executor_running', changedFiles: 2 })).toContain('2');
  });

  it('does not claim a Draft PR for completed Sovereign Agent without draftPrUrl', () => {
    const answer = buildExecutorStatusAnswer({ agentState: 'idle', agentStatus: 'completed' });
    expect(answer).toContain('keine Draft-PR-URL');
    expect(answer).not.toContain('Draft PR wurde erstellt');
  });

  it('does not claim draft-pr-ready when agent state lacks draftPrUrl evidence', () => {
    const answer = buildExecutorStatusAnswer({ agentState: 'draft_pr_ready' });
    expect(answer).toContain('keine Draft-PR-URL');
    expect(answer).not.toContain('Draft PR wurde erstellt');
  });
});

describe('delegation and confirmation', () => {
  it('detects delegation and confirmation wording', () => {
    expect(isDelegationIntent('Tu du das fuer mich')).toBe(true);
    expect(isDelegationIntent('Mach das')).toBe(true);
    expect(isDelegationIntent('Ja einbauen')).toBe(true);
  });

  it('delegates only after integration context exists', () => {
    const withContext = [
      { role: 'assistant', text: 'Integrationsauftrag erkannt: Runtime-Router haerten. Bestaetige mit Einbauen.' },
    ];
    const withoutContext = [
      { role: 'user', text: 'Was ist Sovereign Studio?' },
      { role: 'assistant', text: 'Es ist ein Tool.' },
    ];
    expect(hasCodeContextInHistory(withContext)).toBe(true);
    expect(isDelegatedSovereignAgentExecutionIntent('Einbauen', withContext)).toBe(true);
    expect(isDelegatedSovereignAgentExecutionIntent('Mach das fuer mich', withoutContext)).toBe(false);
  });
});

describe('worker action hints', () => {
  it('returns code-route hint for implementation requests', () => {
    expect(getWorkerActionHint({ submittedText: 'Die Oberflaeche soll klarer werden', workerBlocked: false }))
      .toBe('Code-LLM Route · Patch erzeugen');
  });

  it('returns diagnostic hint when worker is blocked and no retry intent', () => {
    expect(getWorkerActionHint({ submittedText: 'Hello world', workerBlocked: true }))
      .toBe('Worker blockiert · lokale Diagnose statt blindem Retry');
  });
});
