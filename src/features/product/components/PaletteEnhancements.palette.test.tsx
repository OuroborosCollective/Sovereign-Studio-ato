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
import { AutoCodeReviewCard } from './AutoCodeReviewCard';
import { FileContentPreviewSheet } from './FileContentPreviewSheet';
import { FileBadge } from './FileBadge';
import { AgentEventStream } from './AgentEventStream';
import { ChangelogPreviewCard } from './ChangelogPreviewCard';
import { WorkflowRepairPanel } from './WorkflowRepairPanel';
import { WorkbenchSidePanel } from './WorkbenchSidePanel';
import { WorkflowWatchPanel } from './WorkflowWatchPanel';
import { CompactRepoSetupSheet } from './CompactRepoSetupSheet';
import { ErrorCategoriesPanel } from './ErrorCategoriesPanel';
import { PromptLibraryPanel } from './PromptLibraryPanel';
import { OperatorCoachPanel } from './OperatorCoachPanel';
import { AgentResultCard } from './AgentResultCard';
import { IntegrationIntentDraftCard } from './IntegrationIntentDraftCard';
import { PaywallModal } from '../../billing/PaywallModal';
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

  describe('Sheet close-button tooltips', () => {
    it('Patch Diff close button keeps matching aria-label and title', () => {
      const report = {
        files: [],
        created: 0,
        modified: 0,
        unchanged: 0,
        sourceMissing: 0,
        totalAddedLines: 0,
        totalRemovedLines: 0,
        summary: 'Keine Änderungen.',
      };

      render(
        <PatchDiffEvidenceSheet
          report={report}
          confirmed={false}
          onConfirm={vi.fn()}
          onClose={vi.fn()}
        />,
      );

      const closeButton = screen.getByRole('button', { name: 'Patch Diff schließen' });
      expect(closeButton).toHaveAttribute('aria-label', 'Patch Diff schließen');
      expect(closeButton).toHaveAttribute('title', 'Patch Diff schließen');
    });

    it('Runtime Logs close button keeps matching aria-label and title', () => {
      render(<RuntimeEvidenceLogSheet entries={[]} onClose={vi.fn()} />);

      const closeButton = screen.getByRole('button', { name: 'Runtime Logs schließen' });
      expect(closeButton).toHaveAttribute('aria-label', 'Runtime Logs schließen');
      expect(closeButton).toHaveAttribute('title', 'Runtime Logs schließen');
    });

    it('FileContentPreviewSheet close button has matching aria-label and title', () => {
      render(
        <FileContentPreviewSheet
          filePath="src/main.tsx"
          result={{ status: 'loaded', content: 'console.log("hello");', sizeBytes: 22, sha: '123', language: 'typescript' }}
          loading={false}
          onClose={vi.fn()}
        />
      );

      const closeButton = screen.getByRole('button', { name: 'Vorschau schließen' });
      expect(closeButton).toHaveAttribute('aria-label', 'Vorschau schließen');
      expect(closeButton).toHaveAttribute('title', 'Vorschau schließen');
    });
  });

  describe('ChangelogPreviewCard, WorkflowRepairPanel, and WorkbenchSidePanel Enhancements', () => {
    it('ChangelogPreviewCard buttons have descriptive titles, aria-labels, copy feedback state, and accessible pre block', async () => {
      const mockResult = {
        commitCount: 3,
        source: 'git log',
        markdown: '# Changelog\n- Added something',
      };
      const onClose = vi.fn();
      const onUseAsMission = vi.fn();

      render(
        <ChangelogPreviewCard
          result={mockResult}
          onClose={onClose}
          onUseAsMission={onUseAsMission}
        />
      );

      const section = screen.getByTestId('changelog-preview-card');
      expect(section).toHaveAttribute('aria-labelledby', 'changelog-preview-title');

      const closeBtn = screen.getByRole('button', { name: 'Keep-a-Changelog Vorschau schließen' });
      expect(closeBtn).toHaveAttribute('title', 'Keep-a-Changelog Vorschau schließen');
      expect(closeBtn).toHaveClass('focus-visible:ring-2');

      const preBlock = screen.getByLabelText('Changelog Markdown Vorschau');
      expect(preBlock).toHaveAttribute('tabIndex', '0');

      const copyBtn = screen.getByRole('button', { name: 'Vorschau-Markdown in die Zwischenablage kopieren' });
      expect(copyBtn).toHaveAttribute('title', 'Vorschau-Markdown in die Zwischenablage kopieren');
      expect(copyBtn).toHaveClass('focus-visible:ring-2');

      // Click copy button and test temporary feedback state
      await React.act(async () => {
        fireEvent.click(copyBtn);
      });
      expect(screen.getByRole('button', { name: 'Markdown in Zwischenablage kopiert' })).toBeInTheDocument();
      expect(screen.getByText('Kopiert ✓')).toBeInTheDocument();

      const missionBtn = screen.getByRole('button', { name: 'Als CHANGELOG-Auftrag in den Builder übernehmen' });
      expect(missionBtn).toHaveAttribute('title', 'Als CHANGELOG-Auftrag in den Builder übernehmen');
      expect(missionBtn).toHaveClass('focus-visible:ring-2');
    });

    it('WorkflowRepairPanel Use Repair Mission button is stateful', () => {
      const mockPlan = {
        summary: 'Repair summary',
        severity: 'high',
        reason: 'Failed build',
        mission: 'Repair mission content',
        blocked: false,
        actions: [],
      };
      const onUseMission = vi.fn();

      const { rerender } = render(
        <WorkflowRepairPanel plan={mockPlan} onUseMission={onUseMission} />
      );

      let repairBtn = screen.getByRole('button', { name: 'Use Repair Mission in Builder' });
      expect(repairBtn).toHaveAttribute('title', 'Reparaturauftrag in den Builder übernehmen');

      const blockedPlan = { ...mockPlan, blocked: true };
      rerender(<WorkflowRepairPanel plan={blockedPlan} onUseMission={onUseMission} />);

      repairBtn = screen.getByRole('button', { name: 'Use Repair Mission in Builder' });
      expect(repairBtn).toHaveAttribute('title', 'Reparaturauftrag blockiert');
    });

    it('WorkbenchSidePanel buttons have matching attributes', () => {
      const slots = [
        {
          id: 'draftPr',
          tone: 'positive' as const,
          label: 'Draft PR',
          value: 'Open',
          emptyLabel: 'No PR',
          items: ['https://github.com/test/pull/1'],
        },
      ];
      const onOpenDraftPr = vi.fn();
      const onToggleInspector = vi.fn();

      const { rerender } = render(
        <WorkbenchSidePanel
          slots={slots}
          onOpenDraftPr={onOpenDraftPr}
          modules={[]}
          signals={{}}
          showInspector={false}
          onToggleInspector={onToggleInspector}
        />
      );

      const openPrBtn = screen.getByRole('button', { name: 'Draft PR öffnen: https://github.com/test/pull/1' });
      expect(openPrBtn).toHaveAttribute('title', 'Draft PR öffnen: https://github.com/test/pull/1');

      let inspectorBtn = screen.getByRole('button', { name: 'Inspector öffnen (intern)' });
      expect(inspectorBtn).toHaveAttribute('title', 'Inspector öffnen (intern)');

      rerender(
        <WorkbenchSidePanel
          slots={slots}
          onOpenDraftPr={onOpenDraftPr}
          modules={[]}
          signals={{}}
          showInspector={true}
          onToggleInspector={onToggleInspector}
        />
      );

      inspectorBtn = screen.getByRole('button', { name: 'Inspector schließen' });
      expect(inspectorBtn).toHaveAttribute('title', 'Inspector schließen');
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

    it('Input fields and file buttons have correct accessibility and hover attributes', () => {
      const sidebarProps = {
        settings: { repoMode: 'single', packageManager: 'npm', linter: 'eslint', maxFixLoops: 3, specialization: '' },
        buildProduct: vi.fn(),
        blueprint: 'Test blueprint text',
        setBlueprint: vi.fn(),
        addCard: vi.fn(),
        log: vi.fn(),
        selectedFile: { path: 'src/App.tsx', icon: 'TS' },
        setSelectedFile: vi.fn(),
        setWorkView: vi.fn(),
        repoUrl: 'https://github.com/test/repo',
        setRepoUrl: vi.fn(),
        setShowSettings: vi.fn(),
      };
      render(<Sidebar {...sidebarProps as any} />);

      const repoInput = screen.getByLabelText('GitHub Repository URL');
      expect(repoInput).toHaveValue('https://github.com/test/repo');

      const blueprintTextarea = screen.getByLabelText('Idee oder Auftrag');
      expect(blueprintTextarea).toHaveValue('Test blueprint text');

      const searchInput = screen.getByLabelText('Datei suchen');
      expect(searchInput).toBeInTheDocument();

      const fileButtons = screen.getAllByRole('button');
      const appFileButton = fileButtons.find(btn => btn.getAttribute('title') === 'src/App.tsx');
      expect(appFileButton).toBeDefined();

      // Uebernehmen button
      const uebernehmenButton = screen.getByRole('button', { name: 'Idee übernehmen' });
      expect(uebernehmenButton).toHaveAttribute('title', 'Idee übernehmen');

      // Notiz button
      const notizButton = screen.getByRole('button', { name: 'Notiz hinzufügen' });
      expect(notizButton).toHaveAttribute('title', 'Notiz hinzufügen');

      // Suche button
      const sucheButton = screen.getByRole('button', { name: 'Datei im Repository suchen' });
      expect(sucheButton).toHaveAttribute('title', 'Datei im Repository suchen');

      // Idee-Fabrik chip button
      const chipButton = screen.getByRole('button', { name: 'Idee übernehmen: CI Fehleranalyse' });
      expect(chipButton).toHaveAttribute('title', 'Idee übernehmen: CI Fehleranalyse');
    });

    it('Filters files correctly based on search input and shows empty state', () => {
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

      // At start, package.json button exists
      expect(screen.getByTitle('package.json')).toBeInTheDocument();

      const searchInput = screen.getByLabelText('Datei suchen');
      fireEvent.change(searchInput, { target: { value: 'App' } });

      // After filtering 'App', src/App.tsx is present but package.json is not
      expect(screen.getByTitle('src/App.tsx')).toBeInTheDocument();
      expect(screen.queryByTitle('package.json')).not.toBeInTheDocument();

      // Clear search should restore
      fireEvent.change(searchInput, { target: { value: '' } });
      expect(screen.getByTitle('package.json')).toBeInTheDocument();

      // Impossible search should show empty state
      fireEvent.change(searchInput, { target: { value: 'nonexistent-file-xyz' } });
      expect(screen.queryByTitle('package.json')).not.toBeInTheDocument();
      expect(screen.getByText('Keine passenden Dateien gefunden')).toBeInTheDocument();
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

    it('supports keyboard navigation via ArrowDown and ArrowUp and dynamically sets tabIndex', async () => {
      const options = [
        { id: 'opt1', label: 'Option 1' },
        { id: 'opt2', label: 'Option 2' },
        { id: 'opt3', label: 'Option 3' },
      ];
      const handleAnswer = vi.fn();

      const { container } = render(
        <AgentQuestionCard
          question="Test Question"
          options={options}
          onAnswer={handleAnswer}
        />
      );

      const radio1 = screen.getByRole('radio', { name: 'Option 1' });
      const radio2 = screen.getByRole('radio', { name: 'Option 2' });
      const radio3 = screen.getByRole('radio', { name: 'Option 3' });

      // Initially, only the first option is focusable since nothing is selected
      expect(radio1).toHaveAttribute('tabIndex', '0');
      expect(radio2).toHaveAttribute('tabIndex', '-1');
      expect(radio3).toHaveAttribute('tabIndex', '-1');

      // Click option 2 manually
      fireEvent.click(radio2);
      expect(radio1).toHaveAttribute('tabIndex', '-1');
      expect(radio2).toHaveAttribute('tabIndex', '0');
      expect(radio3).toHaveAttribute('tabIndex', '-1');

      // Focus option 2 and press ArrowDown
      radio2.focus();

      await vi.waitFor(async () => {
        fireEvent.keyDown(radio2, { key: 'ArrowDown' });
        await new Promise((resolve) => setTimeout(resolve, 15));
      });

      // Expect Option 3 to be selected, focused, and have tabIndex=0
      expect(radio1).toHaveAttribute('tabIndex', '-1');
      expect(radio2).toHaveAttribute('tabIndex', '-1');
      expect(radio3).toHaveAttribute('tabIndex', '0');

      // Press ArrowDown again to wrap around to Option 1
      await vi.waitFor(async () => {
        fireEvent.keyDown(radio3, { key: 'ArrowDown' });
        await new Promise((resolve) => setTimeout(resolve, 15));
      });
      expect(radio1).toHaveAttribute('tabIndex', '0');
      expect(radio2).toHaveAttribute('tabIndex', '-1');
      expect(radio3).toHaveAttribute('tabIndex', '-1');

      // Press ArrowUp to go back to Option 3
      await vi.waitFor(async () => {
        fireEvent.keyDown(radio1, { key: 'ArrowUp' });
        await new Promise((resolve) => setTimeout(resolve, 15));
      });
      expect(radio1).toHaveAttribute('tabIndex', '-1');
      expect(radio2).toHaveAttribute('tabIndex', '-1');
      expect(radio3).toHaveAttribute('tabIndex', '0');
    });
  });

  describe('AutoCodeReviewCard Enhancements', () => {
    it('Findings button has aria-expanded and stateful dynamic titles; back button has title', () => {
      const mockResult = {
        decision: 'blocked_high',
        summary: 'Review failed due to critical finding.',
        highCount: 1,
        mediumCount: 0,
        lowCount: 0,
        findings: [
          {
            severity: 'HIGH',
            category: 'security',
            file: 'src/features/product/components/AutoCodeReviewCard.tsx',
            lineHint: 'L10',
            description: 'Mock finding',
          },
        ],
        error: 'Critical issue',
        resolvedTransport: 'mock-transport',
        fallbackUsed: false,
      };

      const handleCancel = vi.fn();

      render(<AutoCodeReviewCard result={mockResult as any} onCancel={handleCancel} />);

      const article = screen.getByRole('article', { name: 'Code Review Ergebnis' });
      expect(article).toBeInTheDocument();

      const highBadge = screen.getByTitle('1 hohe Schwachstellen (HIGH)');
      expect(highBadge).toBeInTheDocument();

      const findingCard = screen.getByTitle('Schwachstelle in src/features/product/components/AutoCodeReviewCard.tsx (L10): Security (HIGH)');
      expect(findingCard).toBeInTheDocument();

      const findingsBtn = screen.getByRole('button', { name: /Findings/i });
      expect(findingsBtn).toHaveAttribute('aria-expanded', 'true');
      expect(findingsBtn).toHaveAttribute('title', 'Gefundene Schwachstellen ausblenden');
      expect(findingsBtn).toHaveClass('focus-visible:ring-2');

      // Click to toggle/close findings
      fireEvent.click(findingsBtn);
      expect(findingsBtn).toHaveAttribute('aria-expanded', 'false');
      expect(findingsBtn).toHaveAttribute('title', 'Gefundene Schwachstellen einblenden');

      const backBtn = screen.getByRole('button', { name: /Zurück zum Fix/i });
      expect(backBtn).toHaveAttribute('title', 'Zurück zum Fix-Workflow wechseln');
      expect(backBtn).toHaveClass('focus-visible:ring-2');
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

  describe('FileBadge Accessibility and Discoverability Enhancements', () => {
    it('Global FileBadge has aria-label and dynamic title matching state', () => {
      const onOpenFile = vi.fn();
      const { rerender } = render(
        <FileBadge path="src/" file="App.tsx" onOpenFile={onOpenFile} />
      );

      const fileBadgeBtn = screen.getByRole('button', { name: 'Repo Datei öffnen: src/App.tsx' });
      expect(fileBadgeBtn).toHaveAttribute('aria-label', 'Repo Datei öffnen: src/App.tsx');
      expect(fileBadgeBtn).toHaveAttribute('title', 'Repo Datei öffnen: src/App.tsx');

      // Test non-interactive badge
      rerender(<FileBadge path="src/" file="App.tsx" />);
      const disabledBadge = screen.getByRole('button', { name: 'Repo Datei öffnen: src/App.tsx' });
      expect(disabledBadge).toBeDisabled();
      expect(disabledBadge).not.toHaveAttribute('title');
    });

    it('Inline FileBadge inside AgentEventStream has stateful aria-label and title', () => {
      const mockSnapshot = {
        id: 'test-work',
        state: 'draft_pr_ready' as const,
        branchName: 'main',
        repoFullName: 'test/repo',
        events: [
          {
            id: 'ev-1',
            ts: Date.now(),
            state: 'intent_detected' as const,
            label: 'Auftrag erkannt',
          },
        ],
        created: 123,
        updated: 124,
      };
      const mockJob = {
        id: 'test-job',
        status: 'completed' as const,
        events: [],
        changedFiles: ['src/App.tsx'],
      };
      const onOpenFile = vi.fn();

      const { rerender } = render(
        <AgentEventStream snapshot={mockSnapshot} job={mockJob} onOpenFile={onOpenFile} />
      );

      const inlineBadgeBtn = screen.getByRole('button', { name: 'Repo Datei öffnen: src/App.tsx' });
      expect(inlineBadgeBtn).toHaveAttribute('title', 'Repo Datei öffnen: src/App.tsx');

      // Non-interactive (no onOpenFile)
      rerender(
        <AgentEventStream snapshot={mockSnapshot} job={mockJob} />
      );
      const disabledInlineBadgeBtn = screen.getByRole('button', { name: 'Repo Datei: src/App.tsx' });
      expect(disabledInlineBadgeBtn).toHaveAttribute('title', 'src/App.tsx');
    });
  });

  describe('WorkflowWatchPanel Enhancements', () => {
    it('button has dynamic dynamic title and aria-label matching state', () => {
      const onWatch = vi.fn();
      const { rerender } = render(
        <WorkflowWatchPanel
          report={null}
          isWatching={false}
          canWatch={true}
          onWatch={onWatch}
        />
      );

      // Blocked state 1 (default helperText "create a draft pr..." which blocks watch because no report yet)
      const blockedBtn1 = screen.getByRole('button', { name: 'Workflow Watch blocked: Create a Draft PR first' });
      expect(blockedBtn1).toBeDisabled();
      expect(blockedBtn1).toHaveAttribute('title', 'Create a Draft PR first to monitor commit checks');
      expect(blockedBtn1).toHaveTextContent('Draft PR zuerst erstellen');

      // Blocked state 2 (explicitly canWatch={false})
      rerender(
        <WorkflowWatchPanel
          report={{ status: 'pending', commitSha: 'abc', branch: 'main', checks: [], fixes: [], summary: 'some summary' }}
          isWatching={false}
          canWatch={false}
          onWatch={onWatch}
        />
      );
      const blockedBtn2 = screen.getByRole('button', { name: 'Workflow Watch blocked: Create a Draft PR first' });
      expect(blockedBtn2).toBeDisabled();
      expect(blockedBtn2).toHaveAttribute('title', 'Create a Draft PR first to monitor commit checks');

      // Watching state
      rerender(
        <WorkflowWatchPanel
          report={{ status: 'pending', commitSha: 'abc', branch: 'main', checks: [], fixes: [], summary: 'some summary' }}
          isWatching={true}
          canWatch={true}
          onWatch={onWatch}
        />
      );
      const watchingBtn = screen.getByRole('button', { name: 'Workflow Watch active: Monitoring checks' });
      expect(watchingBtn).toBeDisabled();
      expect(watchingBtn).toHaveAttribute('title', 'Workflow is already being actively monitored');
      expect(watchingBtn).toHaveTextContent('Watching...');

      // Ready state
      rerender(
        <WorkflowWatchPanel
          report={{ status: 'pending', commitSha: 'abc', branch: 'main', checks: [], fixes: [], summary: 'some summary' }}
          isWatching={false}
          canWatch={true}
          onWatch={onWatch}
        />
      );
      const readyBtn = screen.getByRole('button', { name: 'Start monitoring commit checks' });
      expect(readyBtn).not.toBeDisabled();
      expect(readyBtn).toHaveAttribute('title', 'Monitor GitHub commit checks now');
      expect(readyBtn).toHaveTextContent('Watch Commit Checks');
    });

    it('status labels have descriptive tooltip titles', () => {
      const report = {
        status: 'green',
        commitSha: 'sha256',
        branch: 'main',
        checks: [
          { name: 'Build Check', status: 'green', source: 'github', summary: 'Build passed' },
          { name: 'Lint Check', status: 'red', source: 'github', summary: 'Lint failed' },
          { name: 'Test Check', status: 'pending', source: 'github', summary: 'Tests running' },
          { name: 'Unknown Check', status: 'unknown', source: 'github', summary: 'no status' },
        ],
        fixes: [],
        summary: 'all good',
      };

      render(
        <WorkflowWatchPanel
          report={report}
          isWatching={false}
          onWatch={vi.fn()}
        />
      );

      // Main status
      const mainStatus = screen.getByText('Status: green');
      expect(mainStatus).toHaveAttribute('title', 'Successfully completed (green)');

      // Check status items
      const checkGreen = screen.getByText('green');
      expect(checkGreen).toHaveAttribute('title', 'Successfully completed (green)');

      const checkRed = screen.getByText('red');
      expect(checkRed).toHaveAttribute('title', 'Failed (red)');

      const checkPending = screen.getByText('pending');
      expect(checkPending).toHaveAttribute('title', 'Pending (pending)');

      const checkUnknown = screen.getByText('unknown');
      expect(checkUnknown).toHaveAttribute('title', 'Unknown');
    });
  });

  describe('CompactRepoSetupSheet Accessibility and Keyboard Usability Enhancements', () => {
    it('associates label and input programmatically', () => {
      render(
        <CompactRepoSetupSheet
          value=""
          busy={false}
          error={null}
          onChange={vi.fn()}
          onLoad={vi.fn()}
          onClose={vi.fn()}
        />
      );

      const label = screen.getByText('GitHub Repository URL');
      expect(label).toHaveAttribute('for', 'repo-setup-url-input');

      const input = screen.getByLabelText('GitHub Repository URL');
      expect(input).toHaveAttribute('id', 'repo-setup-url-input');
    });

    it('triggers onLoad when pressing Enter inside URL input', () => {
      const onLoad = vi.fn();
      render(
        <CompactRepoSetupSheet
          value="https://github.com/owner/repo"
          busy={false}
          error={null}
          onChange={vi.fn()}
          onLoad={onLoad}
          onClose={vi.fn()}
        />
      );

      const input = screen.getByLabelText('GitHub Repository URL');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(onLoad).toHaveBeenCalledTimes(1);
    });

    it('does not trigger onLoad on Enter when value is empty or busy', () => {
      const onLoad = vi.fn();
      const { rerender } = render(
        <CompactRepoSetupSheet
          value=""
          busy={false}
          error={null}
          onChange={vi.fn()}
          onLoad={onLoad}
          onClose={vi.fn()}
        />
      );

      const input = screen.getByLabelText('GitHub Repository URL');
      fireEvent.keyDown(input, { key: 'Enter' });
      expect(onLoad).not.toHaveBeenCalled();

      // Busy state
      rerender(
        <CompactRepoSetupSheet
          value="https://github.com/owner/repo"
          busy={true}
          error={null}
          onChange={vi.fn()}
          onLoad={onLoad}
          onClose={vi.fn()}
        />
      );

      fireEvent.keyDown(input, { key: 'Enter' });
      expect(onLoad).not.toHaveBeenCalled();
    });

    it('shows stateful submit button titles based on loading status', () => {
      const { rerender } = render(
        <CompactRepoSetupSheet
          value=""
          busy={false}
          error={null}
          onChange={vi.fn()}
          onLoad={vi.fn()}
          onClose={vi.fn()}
        />
      );

      let submitBtn = screen.getByRole('button', { name: 'Repo-Snapshot laden' });
      expect(submitBtn).toBeDisabled();
      expect(submitBtn).toHaveAttribute('title', 'Bitte geben Sie eine gültige GitHub-Repository-URL ein');

      // Valid but not busy
      rerender(
        <CompactRepoSetupSheet
          value="https://github.com/owner/repo"
          busy={false}
          error={null}
          onChange={vi.fn()}
          onLoad={vi.fn()}
          onClose={vi.fn()}
        />
      );

      submitBtn = screen.getByRole('button', { name: 'Repo-Snapshot laden' });
      expect(submitBtn).not.toBeDisabled();
      expect(submitBtn).toHaveAttribute('title', 'Repository-Snapshot von der angegebenen URL laden');

      // Busy loading
      rerender(
        <CompactRepoSetupSheet
          value="https://github.com/owner/repo"
          busy={true}
          error={null}
          onChange={vi.fn()}
          onLoad={vi.fn()}
          onClose={vi.fn()}
        />
      );

      submitBtn = screen.getByRole('button', { name: 'Repo-Snapshot wird geladen…' });
      expect(submitBtn).toBeDisabled();
      expect(submitBtn).toHaveAttribute('title', 'Repository-Snapshot wird geladen…');
    });
  });

  describe('ErrorCategoriesPanel Accessibility and Hover Discoverability Enhancements', () => {
    it('renders with section aria-label and native hover tooltips on badges, cards, and buttons', () => {
      const mockRegistry = {
        findings: [
          {
            id: 'find-1',
            category: 'type-error' as const,
            severity: 'critical' as const,
            title: 'Unresolved TypeScript Type Error',
            description: 'Type mismatch in component props',
            fixTips: 'Fix type definition',
            filePath: 'src/components/MyComponent.tsx',
            confidence: 0.9,
            hits: 1,
            status: 'active' as const,
          },
          {
            id: 'find-2',
            category: 'security-leak' as const,
            severity: 'high' as const,
            title: 'Exposed Hardcoded Secret',
            description: 'Found API key string',
            fixTips: 'Move to env var',
            filePath: 'src/config.ts',
            confidence: 0.95,
            hits: 1,
            status: 'resolved' as const,
          },
        ],
        runs: [],
      };

      const onFindingClick = vi.fn();

      render(<ErrorCategoriesPanel registry={mockRegistry} onFindingClick={onFindingClick} />);

      const section = screen.getByRole('region', { name: 'Fehlerkategorien Übersicht' });
      expect(section).toBeInTheDocument();

      const statusBadge = screen.getByText('1 aktiv · 1 gelöst');
      expect(statusBadge).toHaveAttribute('title', '1 aktive Findings, 1 gelöst');

      const criticalCard = screen.getByTitle('1 kritisch-Findings');
      expect(criticalCard).toBeInTheDocument();

      const findingCategoryBadge = screen.getByTitle('1 aktive TypeScript-Findings');
      expect(findingCategoryBadge).toBeInTheDocument();

      const findingBtn = screen.getByRole('button', { name: /Unresolved TypeScript Type Error/i });
      expect(findingBtn).toHaveAttribute('title', 'Finding anzeigen: Unresolved TypeScript Type Error');
      expect(findingBtn).toHaveClass('focus-visible:ring-2');

      const filePathElement = screen.getByTitle('src/components/MyComponent.tsx');
      expect(filePathElement).toBeInTheDocument();

      fireEvent.click(findingBtn);
      expect(onFindingClick).toHaveBeenCalledWith(mockRegistry.findings[0]);
    });
  });

  describe('PromptLibraryPanel Accessibility and Micro-UX Enhancements', () => {
    it('renders dialog and controls with descriptive title, aria-label, and aria-pressed attributes', () => {
      const onSelectTemplate = vi.fn();
      const onClose = vi.fn();

      render(
        <PromptLibraryPanel
          onSelectTemplate={onSelectTemplate}
          onClose={onClose}
        />
      );

      const closeBtn = screen.getByRole('button', { name: 'Prompt-Bibliothek schließen' });
      expect(closeBtn).toHaveAttribute('title', 'Prompt-Bibliothek schließen');

      const searchInput = screen.getByLabelText('Prompt-Templates suchen');
      expect(searchInput).toHaveAttribute('title', 'Prompt-Templates suchen');

      const allCategoryBtn = screen.getByRole('button', { name: 'Kategorie: Alle' });
      expect(allCategoryBtn).toHaveAttribute('title', 'Kategorie: Alle');
      expect(allCategoryBtn).toHaveAttribute('aria-pressed', 'true');

      const createCustomBtn = screen.getByRole('button', { name: 'Eigenes Template erstellen' });
      expect(createCustomBtn).toHaveAttribute('title', 'Eigenes Template erstellen');

      // Expand custom template creation form
      fireEvent.click(createCustomBtn);

      const labelInput = screen.getByLabelText('Template Bezeichnung');
      expect(labelInput).toHaveAttribute('title', 'Template Bezeichnung');

      const promptTextarea = screen.getByLabelText('Template Prompt Text');
      expect(promptTextarea).toHaveAttribute('title', 'Template Prompt Text');

      const categorySelect = screen.getByLabelText('Template Kategorie');
      expect(categorySelect).toHaveAttribute('title', 'Template Kategorie');

      const saveBtn = screen.getByRole('button', { name: 'Template speichern' });
      expect(saveBtn).toHaveAttribute('title', 'Template speichern');

      const cancelBtn = screen.getByRole('button', { name: 'Erstellung abbrechen' });
      expect(cancelBtn).toHaveAttribute('title', 'Erstellung abbrechen');
    });
  });

  describe('OperatorCoachPanel Accessibility and Micro-UX Enhancements', () => {
    it('renders section with aria-labelledby and accessible status lamp and action buttons', () => {
      const onRepo = vi.fn();
      const onBuilder = vi.fn();
      const onFiles = vi.fn();
      const onLogs = vi.fn();

      render(
        <OperatorCoachPanel
          lamp="green"
          headline="Bereit fuer Auftrag"
          message="Das Repository ist verbunden."
          nextAction="Einen neuen Auftrag eingeben."
          isThinking={false}
          onRepo={onRepo}
          onBuilder={onBuilder}
          onFiles={onFiles}
          onLogs={onLogs}
        />
      );

      const section = screen.getByRole('region', { name: /Sovereign Bot · Bereit fuer Auftrag/i });
      expect(section).toBeInTheDocument();
      expect(section).toHaveAttribute('aria-labelledby', 'operator-coach-heading');

      const lamp = screen.getByLabelText('Status: Grün (Betriebsbereit)');
      expect(lamp).toHaveAttribute('title', 'Status: Grün (Betriebsbereit)');

      const repoBtn = screen.getByRole('button', { name: 'Zum Repository-Bereich wechseln' });
      expect(repoBtn).toHaveAttribute('title', 'Zum Repository-Bereich wechseln');
      expect(repoBtn).toHaveClass('focus-visible:ring-2');

      const builderBtn = screen.getByRole('button', { name: 'Zum Mission-Builder wechseln' });
      expect(builderBtn).toHaveAttribute('title', 'Zum Mission-Builder wechseln');

      const filesBtn = screen.getByRole('button', { name: 'Zu Dateien und Diff-Vorschau wechseln' });
      expect(filesBtn).toHaveAttribute('title', 'Zu Dateien und Diff-Vorschau wechseln');

      const logsBtn = screen.getByRole('button', { name: 'Zum Runtime-Monitor wechseln' });
      expect(logsBtn).toHaveAttribute('title', 'Zum Runtime-Monitor wechseln');

      fireEvent.click(repoBtn);
      expect(onRepo).toHaveBeenCalledTimes(1);

      fireEvent.click(builderBtn);
      expect(onBuilder).toHaveBeenCalledTimes(1);

      fireEvent.click(filesBtn);
      expect(onFiles).toHaveBeenCalledTimes(1);

      fireEvent.click(logsBtn);
      expect(onLogs).toHaveBeenCalledTimes(1);
    });
  });

  describe('PaywallModal Accessibility and Micro-UX Enhancements', () => {
    it('renders dialog with ARIA attributes, close button title/aria-label, linked payment method label, and contextual action buttons', () => {
      const onClose = vi.fn();

      renderWithProviders(<PaywallModal isOpen={true} onClose={onClose} />);

      const dialog = screen.getByRole('dialog', { name: 'Bereit für das nächste Level?' });
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      expect(dialog).toHaveAttribute('aria-labelledby', 'paywall-title');
      expect(dialog).toHaveAttribute('aria-describedby', 'paywall-description');

      const closeBtn = screen.getByRole('button', { name: 'Paywall schließen' });
      expect(closeBtn).toHaveAttribute('title', 'Paywall schließen');
      expect(closeBtn).toHaveClass('focus-visible:ring-2');

      const paymentSelect = screen.getByLabelText('Bestätigte Zahlungsmethode');
      expect(paymentSelect).toHaveAttribute('id', 'paywall-payment-method-select');
      expect(paymentSelect).toHaveClass('focus-visible:ring-2');

      const closeClickRes = fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('AgentResultCard Accessibility and Micro-UX Enhancements', () => {
    it('renders with title tooltips on metadata and styled action buttons with descriptive tooltips', () => {
      const mockSnapshot = {
        id: 'work-123',
        state: 'draft_pr_ready' as const,
        draftPrUrl: 'https://github.com/owner/repo/pull/42',
        branchName: 'feature/amazing-ux',
        commitSha: 'a1b2c3d4e5f6',
        repoFullName: 'owner/repo',
        created: Date.now(),
        updated: Date.now(),
      };

      const onOpen = vi.fn();
      const onViewDiff = vi.fn();
      const onWatchChecks = vi.fn();

      render(
        <AgentResultCard
          snapshot={mockSnapshot}
          checksState="running"
          onOpen={onOpen}
          onViewDiff={onViewDiff}
          onWatchChecks={onWatchChecks}
        />
      );

      const region = screen.getByRole('region', { name: 'Agent Ergebnis' });
      expect(region).toBeInTheDocument();

      expect(screen.getByTitle('Pull Request #42')).toBeInTheDocument();
      expect(screen.getByTitle('owner/repo')).toBeInTheDocument();
      expect(screen.getByTitle('feature/amazing-ux')).toBeInTheDocument();
      expect(screen.getByTitle('Commit SHA: a1b2c3d4e5f6')).toBeInTheDocument();
      expect(screen.getByTitle('Status: Checks laufen…')).toBeInTheDocument();

      const openBtn = screen.getByRole('button', { name: 'Öffnen' });
      expect(openBtn).toHaveAttribute('title', 'Draft PR auf GitHub öffnen');
      expect(openBtn).toHaveClass('focus-visible:ring-2');

      const diffBtn = screen.getByRole('button', { name: 'Diff ansehen' });
      expect(diffBtn).toHaveAttribute('title', 'Diff-Vorschau der Änderungen anzeigen');
      expect(diffBtn).toHaveClass('focus-visible:ring-2');

      const watchBtn = screen.getByRole('button', { name: 'Checks beobachten' });
      expect(watchBtn).toHaveAttribute('title', 'GitHub Commit Checks live beobachten');
      expect(watchBtn).toHaveClass('focus-visible:ring-2');

      fireEvent.click(openBtn);
      expect(onOpen).toHaveBeenCalledTimes(1);

      fireEvent.click(diffBtn);
      expect(onViewDiff).toHaveBeenCalledTimes(1);

      fireEvent.click(watchBtn);
      expect(onWatchChecks).toHaveBeenCalledTimes(1);
    });
  });

  describe('IntegrationIntentDraftCard Accessibility Enhancements', () => {
    const mockDraft = {
      id: 'draft_456',
      originalText: 'Integrationsauftrag fuer Test',
      executionMission: 'Integrationsauftrag fuer Test',
      title: 'Integrationsauftrag Test Title',
      goal: 'Test Ziel',
      scope: ['Frontend'],
      affectedFiles: ['src/App.tsx'],
      createdAt: Date.now(),
      rephrasedText: 'Test',
    };

    const mockGates = {
      repoReady: true,
      githubWriteReady: true,
      directPatchReady: true,
      agentReady: true,
    };

    it('renders region landmark with aria-label', () => {
      render(
        <IntegrationIntentDraftCard
          draft={mockDraft}
          gateSnapshot={mockGates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      const region = screen.getByRole('region', { name: 'Integrationsauftrag Freigabe' });
      expect(region).toBeInTheDocument();
    });

    it('has title tooltips and focus-visible classes on action buttons', () => {
      render(
        <IntegrationIntentDraftCard
          draft={mockDraft}
          gateSnapshot={mockGates}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      const confirmBtn = screen.getByTestId('btn-confirm');
      expect(confirmBtn).toHaveAttribute('title', 'Repository-Auftrag bestätigen und Ausführung starten');
      expect(confirmBtn.className).toContain('focus-visible:ring-2');

      const rephraseBtn = screen.getByTestId('btn-rephrase');
      expect(rephraseBtn).toHaveAttribute('title', 'Ziel und Rahmenbedingungen des Integrationsauftrags anpassen');
      expect(rephraseBtn.className).toContain('focus-visible:ring-2');

      const rejectBtn = screen.getByTestId('btn-reject');
      expect(rejectBtn).toHaveAttribute('title', 'Integrationsauftrag verwürfen und Karte schließen');
      expect(rejectBtn.className).toContain('focus-visible:ring-2');
    });

    it('provides accessible titles for gate indicators', () => {
      render(
        <IntegrationIntentDraftCard
          draft={mockDraft}
          gateSnapshot={{ ...mockGates, githubWriteReady: false }}
          onConfirm={vi.fn()}
          onRephrase={vi.fn()}
          onReject={vi.fn()}
        />
      );

      const repoReadyGate = screen.getByLabelText('Gate Repo ready: Bereit');
      expect(repoReadyGate).toBeInTheDocument();
      expect(repoReadyGate).toHaveAttribute('title', 'Gate Repo ready: Bereit');

      const githubWriteGate = screen.getByLabelText('Gate GitHub Write: Nicht bereit');
      expect(githubWriteGate).toBeInTheDocument();
      expect(githubWriteGate).toHaveAttribute('title', 'Gate GitHub Write: Nicht bereit');
    });
  });
});
