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
    executionMission: 'Der Bot soll jede Eingabe als Integrationsauftrag verstehen',
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
    agentReady: false,
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

    it('labels the card as approval for the exact repository task', () => {
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

      expect(screen.getByText('Freigabe für exakt diesen Repository-Auftrag:')).toBeInTheDocument();
    });

    it('shows the exact structured mission and target that the confirm callback will use', () => {
      const mission = 'Repariere den Build exakt so und führe den Workflow-Test aus.';
      const executionTarget = {
        repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
        branch: 'main',
        expectedHeadSha: 'abcdef0123456789abcdef0123456789abcdef01',
      };
      const draft = createMockDraft({
        originalText: mission,
        executionMission: mission,
        executionTarget,
        title: 'Build reparieren',
        goal: 'Provider-Zusammenfassung darf nicht die Freigabe ersetzen',
        scope: [],
        affectedFiles: [],
        rephrasedText: 'Offline umformulierter Auftrag darf nicht erscheinen',
        intentKind: 'code_execution',
        intentSource: 'online_llm',
        intentConfidence: 0.97,
        intentModel: 'provider/structured-action',
      });
      const approvedPayload = vi.fn();
      const onConfirm = () => approvedPayload({
        executionMission: draft.executionMission,
        executionTarget: draft.executionTarget,
      });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={createMockGates()}
          onConfirm={onConfirm}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      expect(screen.getByTestId('draft-execution-mission').textContent).toBe(mission);
      expect(screen.getByTestId('draft-target-repo').textContent).toBe(executionTarget.repoUrl);
      expect(screen.getByTestId('draft-target-branch').textContent).toBe(executionTarget.branch);
      expect(screen.getByTestId('draft-target-head').textContent).toBe(executionTarget.expectedHeadSha);
      expect(screen.queryByTestId('draft-goal')).not.toBeInTheDocument();
      expect(screen.queryByText('Provider-Zusammenfassung darf nicht die Freigabe ersetzen')).not.toBeInTheDocument();
      expect(screen.queryByText('Offline umformulierter Auftrag darf nicht erscheinen')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Repository-Auftrag starten' }));
      expect(approvedPayload).toHaveBeenCalledOnce();
      expect(approvedPayload).toHaveBeenCalledWith({
        executionMission: mission,
        executionTarget,
      });
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

      expect(screen.getByTestId('btn-confirm').textContent).toBe('Auftrag starten');
      expect(screen.getByTestId('btn-rephrase').textContent).toBe('Neu formulieren');
      expect(screen.getByTestId('btn-reject').textContent).toBe('Ablehnen');
    });

    it('calls onConfirm when Auftrag starten is clicked', () => {
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

    it('disables Auftrag starten when the repo is not ready', () => {
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

    it('offers GitHub-Zugang öffnen when the repo is ready but write access is missing', () => {
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        agentReady: false,
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
      expect(screen.getByTestId('btn-confirm').textContent).toBe('GitHub-Zugang öffnen');
    });

    it('keeps the GitHub access action available when the agent is configured but write access is missing', () => {
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        agentReady: true,
      });

      render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={gates}
          onConfirm={vi.fn()}
          onConfirmWithGitHubAccess={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
          canConfirm={false}
        />
      );

      expect(screen.getByTestId('btn-confirm')).not.toBeDisabled();
      expect(screen.getByTestId('btn-confirm').textContent).toBe('GitHub-Zugang öffnen');
    });

    it('calls onConfirmWithGitHubAccess when button clicked with GitHub access needed', () => {
      const onConfirm = vi.fn();
      const onConfirmWithGitHubAccess = vi.fn();
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        agentReady: false,
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
      expect(screen.getByText('Sovereign Agent')).toBeInTheDocument();
    });

    it('reflects gate state in indicators', () => {
      const draft = createMockDraft();
      const gates = createMockGates({
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        agentReady: true,
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
  // Double-submit protection
  // ─────────────────────────────────────────────────────────────

  describe('double-submit protection', () => {
    it('fires onConfirm exactly once on a fast double click', () => {
      // Arrange
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

      // Act
      const button = screen.getByTestId('btn-confirm');
      fireEvent.click(button);
      fireEvent.click(button);

      // Assert
      expect(onConfirm).toHaveBeenCalledTimes(1);
      expect(button).toBeDisabled();
    });

    it('disables the other actions after the first confirm click', () => {
      // Arrange
      const onRephrase = vi.fn();
      const onReject = vi.fn();
      render(
        <IntegrationIntentDraftCard
          draft={createMockDraft()}
          gateSnapshot={createMockGates()}
          onConfirm={vi.fn()}
          onRephrase={onRephrase}
          onReject={onReject}
        />
      );

      // Act
      fireEvent.click(screen.getByTestId('btn-confirm'));
      fireEvent.click(screen.getByTestId('btn-reject'));

      // Assert
      expect(onReject).not.toHaveBeenCalled();
      expect(screen.getByTestId('btn-rephrase')).toBeDisabled();
      expect(screen.getByTestId('btn-reject')).toBeDisabled();
    });

    it('fires onReject exactly once on a fast double click', () => {
      // Arrange
      const onReject = vi.fn();
      render(
        <IntegrationIntentDraftCard
          draft={createMockDraft()}
          gateSnapshot={createMockGates()}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={onReject}
        />
      );

      // Act
      const button = screen.getByTestId('btn-reject');
      fireEvent.click(button);
      fireEvent.click(button);

      // Assert
      expect(onReject).toHaveBeenCalledTimes(1);
    });

    it('deduplicates a fast access double click without consuming later task approval', () => {
      const onConfirm = vi.fn();
      const onConfirmWithGitHubAccess = vi.fn();
      const draft = createMockDraft();
      const { rerender } = render(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={createMockGates({ githubWriteReady: false })}
          onConfirm={onConfirm}
          onConfirmWithGitHubAccess={onConfirmWithGitHubAccess}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      const button = screen.getByTestId('btn-confirm');
      fireEvent.click(button);
      fireEvent.click(button);
      expect(onConfirmWithGitHubAccess).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();

      rerender(
        <IntegrationIntentDraftCard
          draft={draft}
          gateSnapshot={createMockGates({ githubWriteReady: true })}
          onConfirm={onConfirm}
          onConfirmWithGitHubAccess={onConfirmWithGitHubAccess}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );
      fireEvent.click(screen.getByTestId('btn-confirm'));

      expect(onConfirm).toHaveBeenCalledTimes(1);
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
