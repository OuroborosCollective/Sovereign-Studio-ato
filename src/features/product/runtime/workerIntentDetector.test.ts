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
  it('keeps free language unknown until the online LLM returns structured intent', () => {
    const implementationText = 'Die Oberflaeche soll ruhiger und eindeutiger werden';
    const questionText = 'Wie sollte die Oberflaeche besser werden?';
    expect(isLikelyIntegrationImplementationIntent(implementationText)).toBe(false);
    expect(isCodeGenerationIntent(implementationText)).toBe(false);
    expect(isLikelyIntegrationImplementationIntent(questionText)).toBe(false);
    expect(isCodeGenerationIntent(questionText)).toBe(false);
  });

  it('accepts explicit code controls without interpreting surrounding language', () => {
    expect(isCodeGenerationIntent('/code Die Oberflaeche soll klarer werden')).toBe(true);
    expect(isCodeGenerationIntent('/fix src/App.tsx')).toBe(true);
    expect(isCodeGenerationIntent('/implement tests')).toBe(true);
    expect(isCodeGenerationIntent('/repo owner/name')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('Hallo')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('retry')).toBe(false);
  });
});

describe('explicit executor intent', () => {
  it('accepts only explicit executor controls', () => {
    expect(isSovereignAgentExecutionIntent('/agent fix this')).toBe(true);
    expect(isSovereignAgentExecutionIntent('/draft-pr create')).toBe(true);
    expect(isSovereignAgentExecutionIntent('Use Sovereign Agent to fix this')).toBe(false);
    expect(isSovereignAgentExecutionIntent('Create a draft PR')).toBe(false);
    expect(isSovereignAgentExecutionIntent('push to main')).toBe(false);
    expect(isSovereignAgentExecutionIntent('commit the changes')).toBe(false);
  });

  it('keeps generic build and fix text out of offline code routing', () => {
    expect(isSovereignAgentExecutionIntent('baue die app')).toBe(false);
    expect(isSovereignAgentExecutionIntent('implementiere feature')).toBe(false);
    expect(isSovereignAgentExecutionIntent('fixe den bug')).toBe(false);
    expect(isCodeGenerationIntent('baue die app')).toBe(false);
    expect(isCodeGenerationIntent('/code baue die app')).toBe(true);
  });
});

describe('retry, diagnostics and status', () => {
  it('accepts only exact retry and diagnostic controls', () => {
    expect(isWorkerRetryIntent('retry')).toBe(true);
    expect(isWorkerRetryIntent('/retry')).toBe(true);
    expect(isWorkerRetryIntent('nochmal')).toBe(false);
    expect(isWorkerDiagnosticQuestion('diagnose')).toBe(true);
    expect(isWorkerDiagnosticQuestion('/diagnose')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Warum funktioniert das nicht?')).toBe(false);
    expect(isWorkerDiagnosticQuestion('Error 500')).toBe(false);
  });

  it('accepts only the explicit status control and reports runtime state honestly', () => {
    expect(isExecutorStatusQuestion('/status')).toBe(true);
    expect(isExecutorStatusQuestion('arbeitet er schon?')).toBe(false);
    expect(isExecutorStatusQuestion('warum passiert nichts?')).toBe(false);
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
  it('returns code-route hint only for an explicit offline code control', () => {
    expect(getWorkerActionHint({ submittedText: 'Die Oberflaeche soll klarer werden', workerBlocked: false }))
      .toBe('');
    expect(getWorkerActionHint({ submittedText: '/code Die Oberflaeche soll klarer werden', workerBlocked: false }))
      .toBe('Code-LLM Route · Patch erzeugen');
  });

  it('reports the blocked online language path without local interpretation', () => {
    expect(getWorkerActionHint({ submittedText: 'Hello world', workerBlocked: true }))
      .toBe('Worker blockiert · keine lokale Sprachdeutung');
  });
});
