import { describe, expect, it } from 'vitest';
import {
  isOpenHandsExecutionIntent,
  isCodeGenerationIntent,
  isLikelyIntegrationImplementationIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
  isDelegationIntent,
  hasCodeContextInHistory,
  isDelegatedOpenHandsExecutionIntent,
  getWorkerActionHint,
  isExecutorStatusQuestion,
  buildExecutorStatusAnswer,
  isAlternativeWriteRouteIntent,
  buildAlternativeRouteStatusAnswer,
} from './workerIntentDetector';

describe('integration intent default', () => {
  it('treats normal non-question text as implementation intent', () => {
    expect(isLikelyIntegrationImplementationIntent('Die Oberfläche soll ruhiger und eindeutiger werden')).toBe(true);
    expect(isOpenHandsExecutionIntent('Die Oberfläche soll ruhiger und eindeutiger werden')).toBe(true);
    expect(isCodeGenerationIntent('Die Oberfläche soll ruhiger und eindeutiger werden')).toBe(true);
  });

  it('keeps questions advisory instead of auto-executing', () => {
    expect(isLikelyIntegrationImplementationIntent('Wie sollte die Oberfläche besser werden?')).toBe(false);
    expect(isOpenHandsExecutionIntent('Wie sollte die Oberfläche besser werden?')).toBe(false);
    expect(isCodeGenerationIntent('Wie sollte die Oberfläche besser werden?')).toBe(false);
  });

  it('keeps repo URLs, slash commands, greetings, retry and alternative-route text out of default execution', () => {
    expect(isLikelyIntegrationImplementationIntent('https://github.com/OuroborosCollective/Sovereign-Studio-ato')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('/repo https://github.com/x/y')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('Hallo')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('retry')).toBe(false);
    expect(isLikelyIntegrationImplementationIntent('ohne OpenHands bitte')).toBe(false);
  });
});

describe('isOpenHandsExecutionIntent', () => {
  it('detects explicit executor and PR wording', () => {
    expect(isOpenHandsExecutionIntent('Use OpenHands to fix this')).toBe(true);
    expect(isOpenHandsExecutionIntent('Create a draft PR')).toBe(true);
    expect(isOpenHandsExecutionIntent('pr erstellen')).toBe(true);
    expect(isOpenHandsExecutionIntent('push to main')).toBe(true);
    expect(isOpenHandsExecutionIntent('commit the changes')).toBe(true);
  });

  it('now treats generic build/implement/fix text as execution candidate', () => {
    expect(isOpenHandsExecutionIntent('baue die app')).toBe(true);
    expect(isOpenHandsExecutionIntent('implementiere feature')).toBe(true);
    expect(isOpenHandsExecutionIntent('fixe den bug')).toBe(true);
    expect(isOpenHandsExecutionIntent('repariere den server')).toBe(true);
  });

  it('returns false for clear non-execution text', () => {
    expect(isOpenHandsExecutionIntent('Hello world')).toBe(false);
    expect(isOpenHandsExecutionIntent('What is this project about?')).toBe(false);
  });
});

describe('isCodeGenerationIntent', () => {
  it('detects code work and implementation-like text', () => {
    expect(isCodeGenerationIntent('baue die app')).toBe(true);
    expect(isCodeGenerationIntent('implementiere feature')).toBe(true);
    expect(isCodeGenerationIntent('fixe den bug')).toBe(true);
    expect(isCodeGenerationIntent('Die App soll GitHub-Fehler sauberer führen')).toBe(true);
  });

  it('does not classify advisory questions as code generation', () => {
    expect(isCodeGenerationIntent('Was ist Sovereign Studio?')).toBe(false);
  });
});

describe('retry and diagnostics', () => {
  it('detects retry keywords', () => {
    expect(isWorkerRetryIntent('retry')).toBe(true);
    expect(isWorkerRetryIntent('erneut')).toBe(true);
    expect(isWorkerRetryIntent('nochmal')).toBe(true);
  });

  it('detects diagnostic wording', () => {
    expect(isWorkerDiagnosticQuestion('Warum funktioniert das nicht?')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Cloudflare worker blocked')).toBe(true);
    expect(isWorkerDiagnosticQuestion('Error 500')).toBe(true);
  });
});

describe('delegation and confirmation', () => {
  it('detects classic delegation and integration confirmation wording', () => {
    expect(isDelegationIntent('Tu du das für mich')).toBe(true);
    expect(isDelegationIntent('Mach das')).toBe(true);
    expect(isDelegationIntent('Setz das um')).toBe(true);
    expect(isDelegationIntent('Ja einbauen')).toBe(true);
    expect(isDelegationIntent('Übernehmen')).toBe(true);
  });

  it('recognizes integration context in history', () => {
    const history = [
      { role: 'assistant', text: 'Integrationsauftrag erkannt: Runtime-Router härten. Bestätige mit Einbauen.' },
    ];
    expect(hasCodeContextInHistory(history)).toBe(true);
    expect(isDelegatedOpenHandsExecutionIntent('Einbauen', history)).toBe(true);
  });

  it('does not delegate after pure chat context', () => {
    const history = [
      { role: 'user', text: 'Was ist Sovereign Studio?' },
      { role: 'assistant', text: 'Es ist ein Tool.' },
    ];
    expect(isDelegatedOpenHandsExecutionIntent('Mach das für mich', history)).toBe(false);
  });
});

describe('executor status', () => {
  it('detects executor status questions', () => {
    expect(isExecutorStatusQuestion('arbeitet er schon?')).toBe(true);
    expect(isExecutorStatusQuestion('läuft das?')).toBe(true);
    expect(isExecutorStatusQuestion('warum passiert nichts?')).toBe(true);
  });

  it('reports idle and running honestly', () => {
    expect(buildExecutorStatusAnswer({ agentState: 'idle' })).toContain('nicht');
    expect(buildExecutorStatusAnswer({ agentState: 'executor_running', changedFiles: 2 })).toContain('2');
  });
});

describe('worker action hints', () => {
  it('returns executor hint for implementation requests', () => {
    expect(getWorkerActionHint({ submittedText: 'Die Oberfläche soll klarer werden', workerBlocked: false }))
      .toBe('Executor-Schreibroute starten');
  });

  it('returns diagnostic hint when worker is blocked and no retry intent', () => {
    expect(getWorkerActionHint({ submittedText: 'Hello world', workerBlocked: true }))
      .toBe('Worker blockiert · lokale Diagnose statt blindem Retry');
  });
});

describe('alternative write route', () => {
  it('detects alternative/direct GitHub patch wording', () => {
    expect(isAlternativeWriteRouteIntent('nicht openhands bitte')).toBe(true);
    expect(isAlternativeWriteRouteIntent('direkt über GitHub patchen')).toBe(true);
    expect(isAlternativeWriteRouteIntent('GitHub Patch Route')).toBe(true);
  });

  it('reports GitHub and executor state truthfully', () => {
    expect(buildAlternativeRouteStatusAnswer({
      githubAccessReady: false,
      githubAccessState: 'validating',
      openhandsReady: false,
      directPatchAvailable: false,
    })).toContain('wird gerade geprüft');

    expect(buildAlternativeRouteStatusAnswer({
      githubAccessReady: true,
      githubAccessState: 'ready',
      openhandsReady: false,
      directPatchAvailable: false,
    })).toContain('OpenHands ist nicht konfiguriert');
  });
});
