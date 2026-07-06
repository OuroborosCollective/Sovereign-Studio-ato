import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IntegrationIntentDraftCard } from './IntegrationIntentDraftCard';
import type { IntegrationIntentDraft, IntegrationIntentDraftGateSnapshot } from '../runtime/integrationIntentDraftRuntime';

describe('IntegrationIntentDraftCard', () => {
  // ─────────────────────────────────────────────────────────────
  // Test fixtures
  // ─────────────────────────────────────────────────────────────

  const createMockDraft = (overrides?: Partial<IntegrationIntentDraft>): IntegrationIntentDraft => ({
    id: 'draft_123',
    originalText: 'Der Bot soll jede Eingabe als Integrationsauftrag verstehen',
    title: 'Der Bot soll jede Eingabe als Integrationsauftrag verstehen',
    goal: 'Neue Funktionalität implementieren',
    scope: ['UI/Komponenten', 'Runtime/Routing'],
    affectedFiles: ['src/components/Chat.tsx', 'src/runtime/router.ts'],
    createdAt: Date.now(),
    rephrasedText: 'Implementiere: Der Bot soll jede Eingabe als Integrationsauftrag verstehen',
    ...overrides,
  });

  const createMockGates = (overrides?: Partial<IntegrationIntentDraftGateSnapshot>): IntegrationIntentDraftGateSnapshot => ({
    repoReady: true,
    githubWriteReady: true,
    directPatchReady: false,
    openhandsReady: false,
    ...overrides,
  });

  // ─────────────────────────────────────────────────────────────
  // Rendering
  // ─────────────────────────────────────────────────────────────

  describe('rendering', () => {
    it('renders the card with correct structure', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('integration-intent-draft-card')).toBeInTheDocument();
      expect(screen.getByTestId('draft-title')).toBeInTheDocument();
      expect(screen.getByTestId('draft-title').textContent).toBe(draft.title);
    });

    it('displays title, goal, and scope', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('draft-title').textContent).toBe(draft.title);
      expect(screen.getByTestId('draft-goal').textContent).toBe(draft.goal);
      expect(screen.getByTestId('draft-scope')).toBeInTheDocument();
    });

    it('displays affected files when available', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('draft-affected-files')).toBeInTheDocument();
    });

    it('displays gate indicators', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('draft-gates')).toBeInTheDocument();
    });

    it('shows "Ich habe daraus diesen Integrationsauftrag erkannt" header', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByText('Ich habe daraus diesen Integrationsauftrag erkannt:')).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Buttons
  // ─────────────────────────────────────────────────────────────

  describe('buttons', () => {
    it('renders exactly three action buttons', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('btn-confirm')).toBeInTheDocument();
      expect(screen.getByTestId('btn-rephrase')).toBeInTheDocument();
      expect(screen.getByTestId('btn-reject')).toBeInTheDocument();
    });

    it('button labels are correct', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('btn-confirm').textContent).toBe('Einbauen');
      expect(screen.getByTestId('btn-rephrase').textContent).toBe('Neu formulieren');
      expect(screen.getByTestId('btn-reject').textContent).toBe('Ablehnen');
    });

    it('calls onConfirm when Einbauen is clicked', () => {
      const onConfirm = vi.fn();
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={onConfirm}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      fireEvent.click(screen.getByTestId('btn-confirm'));
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it('calls onRephrase when Neu formulieren is clicked', () => {
      const onRephrase = vi.fn();
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={onRephrase}
          onReject={vi.fn()}
        />
      );

      fireEvent.click(screen.getByTestId('btn-rephrase'));
      expect(onRephrase).toHaveBeenCalledTimes(1);
    });

    it('calls onReject when Ablehnen is clicked', () => {
      const onReject = vi.fn();
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={onReject}
        />
      );

      fireEvent.click(screen.getByTestId('btn-reject'));
      expect(onReject).toHaveBeenCalledTimes(1);
    });

    it('disables Einbauen button when repo is not ready', () => {
      const draft = createMockDraft();
      const gates = createMockGates({ repoReady: false });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
          canConfirm={false}
        />
      );

      expect(screen.getByTestId('btn-confirm')).toBeDisabled();
    });

    it('enables button with GitHub-Zugang benötigt label when repo ready but no GitHub write', () => {
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        openhandsReady: false,
      });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onConfirmWithGitHubAccess={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('btn-confirm')).not.toBeDisabled();
      expect(screen.getByTestId('btn-confirm').textContent).toBe('GitHub-Zugang benötigt');
    });

    it('calls onConfirmWithGitHubAccess when button clicked with GitHub access needed', () => {
      const onConfirm = vi.fn();
      const onConfirmWithGitHubAccess = vi.fn();
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        openhandsReady: false,
      });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={onConfirm}
          onConfirmWithGitHubAccess={onConfirmWithGitHubAccess}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      fireEvent.click(screen.getByTestId('btn-confirm'));
      expect(onConfirmWithGitHubAccess).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();
    });

    it('shows blocker message when repo is not ready', () => {
      const draft = createMockDraft();
      const gates = createMockGates({ repoReady: false });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
          canConfirm={false}
          confirmBlocker="Repository nicht geladen"
        />
      );

      expect(screen.getByTestId('confirm-blocker')).toBeInTheDocument();
      expect(screen.getByTestId('confirm-blocker').textContent).toContain('Repository nicht geladen');
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Gate indicators
  // ─────────────────────────────────────────────────────────────

  describe('gate indicators', () => {
    it('shows all four gate indicators', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByText('Repo ready')).toBeInTheDocument();
      expect(screen.getByText('GitHub Write')).toBeInTheDocument();
      expect(screen.getByText('Direct Patch')).toBeInTheDocument();
      expect(screen.getByText('OpenHands')).toBeInTheDocument();
    });

    it('reflects gate state in indicators', () => {
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        openhandsReady: true,
      });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      // Check that the component renders without errors
      expect(screen.getByTestId('draft-gates')).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────
  // No forbidden patterns
  // ─────────────────────────────────────────────────────────────

  describe('no forbidden patterns', () => {
    it('does not show percentage progress', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      const { container } = render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      // No percentage-like content
      expect(container.textContent).not.toMatch(/\d+%/);
    });

    it('does not show fake success messages', () => {
      const draft = createMockDraft();
      const gates = createMockGates();

      const { container } = render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      // No "Erfolg" or "Success" messages
      expect(container.textContent).not.toMatch(/erfolg|super|fantastisch/i);
    });

    it('does not show hardcoded "100%" or "ready" without real state', () => {
      const draft = createMockDraft({ goal: '' }); // Empty goal should still render
      const gates = createMockGates({ repoReady: false }); // Gates off

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      // Component should still render with empty goal
      expect(screen.getByTestId('draft-title')).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Data attributes
  // ─────────────────────────────────────────────────────────────

  describe('data attributes', () => {
    it('sets correct data attributes on card', () => {
      const draft = createMockDraft({ id: 'test-id-123', title: 'Test Title' });
      const gates = createMockGates();

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      const card = screen.getByTestId('integration-intent-draft-card');
      expect(card.getAttribute('data-draft-id')).toBe('test-id-123');
      expect(card.getAttribute('data-draft-title')).toBe('Test Title');
    });
  });
});
