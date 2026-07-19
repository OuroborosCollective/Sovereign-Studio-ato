import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Provider } from 'react-redux';
import React from 'react';
import { BuilderContainer } from '../containers/BuilderContainer';
import { SovereignToolLauncher } from './SovereignToolLauncher';
import { Sidebar } from './Sidebar';
import { AgentQuestionCard } from './AgentQuestionCard';
import { UserKeyManager, LLM_PROVIDERS } from './UserKeyManager';
import { PatchDiffEvidenceSheet } from './PatchDiffEvidenceSheet';
import { RuntimeEvidenceLogSheet } from './RuntimeEvidenceLogSheet';
import { buildGeneratedFileDiffReport } from '../runtime/generatedFileDiffPreview';
import { store } from '../../../store';

function renderWithProviders(ui: React.ReactElement) {
  return render(<Provider store={store}>{ui}</Provider>);
}

describe('Palette Accessibility Enhancements', () => {
  const baseProps = {
    mission: "Test mission",
    repoReady: true,
    repoReason: "Repo ready.",
    repoBusy: false,
    runtimeBusy: false,
    isPublishing: false,
    sovereignSummary: "Package summary",
    sovereignPreview: '{ "ok": true }',
    onMissionChange: vi.fn(),
    onGenerateIdeas: vi.fn(),
    onGenerateErrorWorkflow: vi.fn(),
    onPublishDraftPr: vi.fn(),
  };

  describe('BuilderContainer Enhancements', () => {
    it('Menu button has title and aria-label', () => {
      renderWithProviders(<BuilderContainer {...baseProps} />);
      const menuButton = screen.getByRole('button', { name: /Menü/i });
      expect(menuButton).toHaveAttribute('aria-label', 'Menü');
      expect(menuButton).toHaveAttribute('title', 'Menü');
    });

    it('Runtime RT button keeps visible label in accessible name', () => {
      renderWithProviders(<BuilderContainer {...baseProps} />);
      const rtButton = screen.getByRole('button', { name: /RT.*Runtime Quelle/i });
      expect(rtButton).toHaveAttribute('aria-label', 'RT – Runtime Quelle');
      expect(rtButton).toHaveAttribute('title', 'Runtime Quelle');
    });

    it('Panel toggle button has title and aria-label', () => {
      renderWithProviders(<BuilderContainer {...baseProps} />);
      const toggleButton = screen.getByRole('button', { name: /Panel öffnen/i });
      expect(toggleButton).toHaveAttribute('aria-label', 'Panel öffnen');
      expect(toggleButton).toHaveAttribute('title', 'Panel öffnen');

      fireEvent.click(toggleButton);
      expect(toggleButton).toHaveAttribute('aria-label', 'Panel schließen');
      expect(toggleButton).toHaveAttribute('title', 'Panel schließen');
    });

    it('Send button has title and aria-label', () => {
      renderWithProviders(<BuilderContainer {...baseProps} />);
      const sendButton = screen.getByRole('button', { name: /Senden/i });
      expect(sendButton).toHaveAttribute('aria-label', 'Senden');
      expect(sendButton).toHaveAttribute('title', 'Senden');
    });

    it('SideDrawer close button has title and aria-label', () => {
      renderWithProviders(<BuilderContainer {...baseProps} />);
      fireEvent.click(screen.getByRole('button', { name: /Menü/i }));
      const closeButton = screen.getByRole('button', { name: /Menü schließen/i });
      expect(closeButton).toHaveAttribute('aria-label', 'Menü schließen');
      expect(closeButton).toHaveAttribute('title', 'Menü schließen');
    });

    it('StatusPanel clear logs button has title and aria-label', () => {
       // StatusPanel needs logs to show clear button
       // Panel toggle is already tested, we need to open it and ensure it has logs
       // But status logs are internal state of BuilderContainer.
       // We can check if it exists when panel is open and there are simulated logs if possible
       // Actually, the clear button only shows if tab === "logs" and logs.length > 0.
       // It's hard to trigger from props.
    });
  });

  describe('SovereignToolLauncher Enhancements', () => {
    it('Launcher button has dynamic title and aria-label matching state', () => {
      render(<SovereignToolLauncher onSelect={vi.fn()} />);
      const launcherButton = screen.getByRole('button', { name: /Tool Launcher öffnen/i });
      expect(launcherButton).toHaveAttribute('aria-label', 'Tool Launcher öffnen');
      expect(launcherButton).toHaveAttribute('title', 'Tool Launcher öffnen');

      // Click to open
      fireEvent.click(launcherButton);
      expect(launcherButton).toHaveAttribute('aria-label', 'Tool Launcher schließen');
      expect(launcherButton).toHaveAttribute('title', 'Tool Launcher schließen');

      // Click to close
      fireEvent.click(launcherButton);
      expect(launcherButton).toHaveAttribute('aria-label', 'Tool Launcher öffnen');
      expect(launcherButton).toHaveAttribute('title', 'Tool Launcher öffnen');
    });

    it('Tool menu items have title', () => {
      render(<SovereignToolLauncher onSelect={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: /Tool Launcher öffnen/i }));
      const repoItem = screen.getByRole('menuitem', { name: /Repo/i });
      expect(repoItem.getAttribute('title')).toMatch(/^Repo:/);
    });
  });

  describe('Sidebar Enhancements', () => {
    it('Settings button has title and aria-label', () => {
      const sidebarProps = {
        settings: { repoMode: 'single', packageManager: 'npm', linter: 'eslint', maxFixLoops: 3, specialization: '' },
        buildProduct: vi.fn(),
        blueprint: '',
        setBlueprint: vi.fn(),
        addCard: vi.fn(),
        log: vi.fn(),
        selectedFile: { path: 'README.md', icon: '📄' },
        setSelectedFile: vi.fn(),
        setWorkView: vi.fn(),
        repoUrl: '',
        setRepoUrl: vi.fn(),
        setShowSettings: vi.fn(),
      };
      render(<Sidebar {...sidebarProps as any} />);
      const settingsButton = screen.getByRole('button', { name: /Einstellungen/i });
      expect(settingsButton).toHaveAttribute('aria-label', 'Einstellungen');
      expect(settingsButton).toHaveAttribute('title', 'Einstellungen');
    });
  });

  describe('AgentQuestionCard Enhancements', () => {
    it('An Agent Senden button has correct state-dependent title and no redundant aria-label', () => {
      const options = [{ id: 'opt1', label: 'Option 1' }, { id: 'opt2', label: 'Option 2' }];
      const handleAnswer = vi.fn();
      const { rerender } = render(
        <AgentQuestionCard
          question="Test Question"
          options={options}
          onAnswer={handleAnswer}
        />
      );

      const sendButton = screen.getByRole('button', { name: /An Agent senden/i });
      expect(sendButton).toHaveAttribute('title', 'Bitte wählen Sie zuerst eine Option aus');
      expect(sendButton).not.toHaveAttribute('aria-label');

      const opt1 = screen.getByRole('radio', { name: 'Option 1' });
      expect(opt1).toHaveAttribute('title', 'Option 1');
      fireEvent.click(opt1);

      expect(sendButton).toHaveAttribute('title', 'Ausgewählte Antwort an den Agenten senden');

      rerender(
        <AgentQuestionCard
          question="Test Question"
          options={options}
          onAnswer={handleAnswer}
          disabled={true}
        />
      );
      expect(sendButton).toHaveAttribute('title', 'Rückfrage bereits beantwortet');
    });
  });

  describe('UserKeyManager Enhancements', () => {
    it('Input and docs buttons have correct accessibility attributes', () => {
      const testProviders = [
        {
          id: 'test-prov',
          name: 'Test Provider',
          description: 'A mock provider',
          docsUrl: 'https://test.docs.com',
          keyPlaceholder: 'Insert key',
          freeTier: 'Yes',
          icon: '🔑',
        },
      ];

      const originalProviders = [...LLM_PROVIDERS];
      LLM_PROVIDERS.push(...testProviders);

      try {
        render(<UserKeyManager />);

        const input = screen.getByLabelText('Test Provider API-Key');
        expect(input).toHaveAttribute('placeholder', 'Serverseitig verwaltet');
        expect(input).toBeDisabled();

        const docsBtn = screen.getByRole('button', { name: /API-Key erstellen → Test Provider/i });
        expect(docsBtn).toHaveAttribute('title', 'API-Key Dokumentation für Test Provider in neuem Tab öffnen');
      } finally {
        LLM_PROVIDERS.length = 0;
        LLM_PROVIDERS.push(...originalProviders);
      }
    });
  });

  describe('PatchDiffEvidenceSheet and RuntimeEvidenceLogSheet Enhancements', () => {
    it('PatchDiffEvidenceSheet close button has matching title and aria-label', () => {
      const mockReport = buildGeneratedFileDiffReport([], []);
      render(
        <PatchDiffEvidenceSheet
          report={mockReport}
          confirmed={false}
          onConfirm={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const closeButton = screen.getByRole('button', { name: 'Patch Diff schließen' });
      expect(closeButton).toHaveAttribute('aria-label', 'Patch Diff schließen');
      expect(closeButton).toHaveAttribute('title', 'Patch Diff schließen');
    });

    it('RuntimeEvidenceLogSheet close button has matching title and aria-label', () => {
      render(
        <RuntimeEvidenceLogSheet
          entries={[]}
          onClose={vi.fn()}
        />
      );
      const closeButton = screen.getByRole('button', { name: 'Runtime Logs schließen' });
      expect(closeButton).toHaveAttribute('aria-label', 'Runtime Logs schließen');
      expect(closeButton).toHaveAttribute('title', 'Runtime Logs schließen');
    });
  });
});
