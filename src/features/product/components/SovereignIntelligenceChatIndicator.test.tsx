import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import {
  SovereignIntelligenceChatIndicator,
  SovereignToolSuccessHint,
  SovereignBlockerWarning,
  SovereignStrategyChangeHint,
} from './SovereignIntelligenceChatIndicator';

describe('SovereignIntelligenceChatIndicator', () => {
  it('renders healthy state correctly', () => {
    render(
      <SovereignIntelligenceChatIndicator
        health="healthy"
        healthReason="Session läuft normal."
        recommendations={[]}
      />
    );

    expect(screen.getByText('✅ Intelligence Feedback')).toBeInTheDocument();
    expect(screen.getByText('Session läuft normal.')).toBeInTheDocument();
  });

  it('renders warning state correctly', () => {
    render(
      <SovereignIntelligenceChatIndicator
        health="warning"
        healthReason="Token fehlt für GitHub Access"
        recommendations={['Strategie überprüfen', 'Fehlende Voraussetzungen identifizieren']}
      />
    );

    expect(screen.getByText('⚠️ Intelligence Feedback')).toBeInTheDocument();
    expect(screen.getByText('Token fehlt für GitHub Access')).toBeInTheDocument();
    expect(screen.getByText('🔄 Strategie überprüfen')).toBeInTheDocument();
  });

  it('renders critical state correctly', () => {
    render(
      <SovereignIntelligenceChatIndicator
        health="critical"
        healthReason="Runtime Fehler aufgetreten"
        recommendations={['Fehler analysieren', 'Alternative Strategie wählen']}
      />
    );

    expect(screen.getByText('🚫 Intelligence Feedback')).toBeInTheDocument();
    expect(screen.getByText(/Fehler analysieren/)).toBeInTheDocument();
  });

  it('renders compact mode', () => {
    render(
      <SovereignIntelligenceChatIndicator
        health="warning"
        healthReason="Session blockiert"
        recommendations={['Strategie überprüfen']}
        blockerCount={3}
        compact
      />
    );

    expect(screen.getByTestId('intelligence-indicator-compact')).toBeInTheDocument();
    expect(screen.getByText(/Session blockiert/)).toBeInTheDocument();
    expect(screen.getByText(/\(3x\)/)).toBeInTheDocument();
  });
});

describe('SovereignToolSuccessHint', () => {
  it('shows first use message', () => {
    render(
      <SovereignToolSuccessHint
        toolName="github_access"
        hasHistory={false}
      />
    );

    expect(screen.getByText(/Erster Einsatz von github_access/)).toBeInTheDocument();
  });

  it('shows successful history', () => {
    render(
      <SovereignToolSuccessHint
        toolName="repo_loader"
        hasHistory={true}
        wasSuccessful={true}
      />
    );

    expect(screen.getByText(/war in früheren Sessions erfolgreich/)).toBeInTheDocument();
  });

  it('shows failed history', () => {
    render(
      <SovereignToolSuccessHint
        toolName="sovereign-agent"
        hasHistory={true}
        wasSuccessful={false}
      />
    );

    expect(screen.getByText(/hatte früher Probleme/)).toBeInTheDocument();
  });
});

describe('SovereignBlockerWarning', () => {
  it('renders blocker warning', () => {
    render(
      <SovereignBlockerWarning
        blocker="missing_token"
        occurrenceCount={3}
      />
    );

    expect(screen.getByText(/missing_token/)).toBeInTheDocument();
    expect(screen.getByText(/\(3x\)/)).toBeInTheDocument();
  });

  it('suggests strategy change after multiple occurrences', () => {
    render(
      <SovereignBlockerWarning
        blocker="auth_failed"
        occurrenceCount={4}
      />
    );

    expect(screen.getByText(/→ Strategie-Wechsel empfohlen/)).toBeInTheDocument();
  });
});

describe('SovereignStrategyChangeHint', () => {
  it('renders strategy change hint', () => {
    render(
      <SovereignStrategyChangeHint
        fromStrategy="sovereign-agent"
        toStrategy="direct-patch"
      />
    );

    expect(screen.getByText(/sovereign-agent → direct-patch/)).toBeInTheDocument();
  });
});
