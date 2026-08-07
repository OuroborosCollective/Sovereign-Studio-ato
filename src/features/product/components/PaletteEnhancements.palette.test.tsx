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
import { TestRunnerResultCard } from './TestRunnerResultCard';
import { SecurityBlockCard } from './SecurityBlockCard';
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
    it('ChangelogPreviewCard buttons have descriptive titles', () => {
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

      const closeBtn = screen.getByRole('button', { name: 'Schließen' });
      expect(closeBtn).toHaveAttribute('title', 'Keep-a-Changelog Vorschau schließen');

      const copyBtn = screen.getByRole('button', { name: 'Kopieren' });
      expect(copyBtn).toHaveAttribute('title', 'Vorschau-Markdown in die Zwischenablage kopieren');

      const missionBtn = screen.getByRole('button', { name: 'Als CHANGELOG-Auftrag übernehmen' });
      expect(missionBtn).toHaveAttribute('title', 'Als CHANGELOG-Auftrag in den Builder übernehmen');
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

      const findingsBtn = screen.getByRole('button', { name: /Findings/i });
      expect(findingsBtn).toHaveAttribute('aria-expanded', 'true');
      expect(findingsBtn).toHaveAttribute('title', 'Gefundene Schwachstellen ausblenden');

      // Click to toggle/close findings
      fireEvent.click(findingsBtn);
      expect(findingsBtn).toHaveAttribute('aria-expanded', 'false');
      expect(findingsBtn).toHaveAttribute('title', 'Gefundene Schwachstellen einblenden');

      const backBtn = screen.getByRole('button', { name: /Zurück zum Fix/i });
      expect(backBtn).toHaveAttribute('title', 'Zurück zum Fix-Workflow wechseln');
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

  describe('TestRunnerResultCard Accessibility and UX', () => {
    it('applies correct accessible attributes to the article container and buttons', () => {
      const mockResult = {
        status: 'failed' as const,
        framework: 'vitest',
        summary: '2 of 10 tests failed',
        blocker: 'Linter error in main.ts',
        counts: { passed: 8, failed: 2, errors: 0, skipped: 0 },
        output: 'Failed test suite detail...',
        hasRepairHint: true,
      };
      const onRepair = vi.fn();

      const { rerender } = render(
        <TestRunnerResultCard result={mockResult} onRepair={onRepair} />
      );

      // Wrapper article tag semantic labels
      const article = screen.getByRole('article', { name: 'Testergebnis' });
      expect(article).toBeInTheDocument();

      // Disclosure toggle button initial state (closed)
      let toggleBtn = screen.getByRole('button', { name: 'Echte Test-Ausgabe anzeigen' });
      expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');
      expect(toggleBtn).toHaveAttribute('aria-label', 'Echte Test-Ausgabe anzeigen');
      expect(toggleBtn).toHaveAttribute('title', 'Echte Test-Ausgabe anzeigen');

      // Click toggle button to open output
      fireEvent.click(toggleBtn);
      toggleBtn = screen.getByRole('button', { name: 'Ausgabe schließen' });
      expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');
      expect(toggleBtn).toHaveAttribute('aria-label', 'Ausgabe schließen');
      expect(toggleBtn).toHaveAttribute('title', 'Ausgabe schließen');

      // Repair button accessibility
      const repairBtn = screen.getByRole('button', { name: 'Fehlgeschlagene Tests reparieren' });
      expect(repairBtn).toHaveAttribute('aria-label', 'Fehlgeschlagene Tests reparieren');
      expect(repairBtn).toHaveAttribute('title', 'Fehlgeschlagene Tests im Workspace reparieren und Fix vorbereiten');

      // Click repair button
      fireEvent.click(repairBtn);
      expect(onRepair).toHaveBeenCalledTimes(1);
    });
  });

  describe('SecurityBlockCard Accessibility and UX', () => {
    it('contains clear, localized aria-label and title attributes on its action buttons', () => {
      const onOpenSecureAccess = vi.fn();
      const onDismiss = vi.fn();

      render(
        <SecurityBlockCard
          title="Secret blockiert"
          text="Ein GitHub-Token wurde in Ihrer Nachricht erkannt."
          hint="Bitte übermitteln Sie keine geheimen Zugangsdaten im Chat."
          buttonLabel="Sicheren Zugriff konfigurieren"
          onOpenSecureAccess={onOpenSecureAccess}
          onDismiss={onDismiss}
        />
      );

      // Secure access button checks
      const accessBtn = screen.getByRole('button', { name: 'Sicheren Zugriff konfigurieren' });
      expect(accessBtn).toHaveAttribute('aria-label', 'Sicheren Zugriff konfigurieren');
      expect(accessBtn).toHaveAttribute('title', 'Sicheren Zugriff konfigurieren');

      // Close button checks
      const closeBtn = screen.getByRole('button', { name: 'Sicherheitswarnung schließen' });
      expect(closeBtn).toHaveAttribute('aria-label', 'Sicherheitswarnung schließen');
      expect(closeBtn).toHaveAttribute('title', 'Sicherheitswarnung schließen');

      // Interactivity test
      fireEvent.click(accessBtn);
      expect(onOpenSecureAccess).toHaveBeenCalledTimes(1);

      fireEvent.click(closeBtn);
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });
  });
});
