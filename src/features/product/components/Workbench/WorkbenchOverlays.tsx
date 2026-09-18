import { C } from '../builderConstants';
import React from 'react';
import type { DevChatRepoSnapshot } from '../../runtime/devChatWorkerBridge';
import type { GitHubAccessState } from '../../runtime/githubAccessRuntime';
import type { SovereignStagedChange } from '../../containers/BuilderContainer';
import type { WorkbenchStatusSlot, WorkbenchStatusSlotId } from '../../runtime/builderWorkbenchStatus';
import { RepoTreeExplorer } from '../RepoTreeExplorer';


import { WorkbenchSlotDrawer } from '../WorkbenchSlotDrawer';

export interface WorkbenchOverlaysProps {
  SideDrawer: React.ComponentType<any>;
  showRepoExplorer: boolean;
  setShowRepoExplorer: (show: boolean) => void;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
  handleRepoExplorerFileClick: (path: string) => Promise<void>;

  showSideMenu: boolean;
  setShowSide: (show: boolean) => void;
  handleOpenAllTools: () => void;
  handleCompactToolSelect: (toolId: any) => void;
  handlePresetActionSelect: (actionId: any) => void;
  handleSideMenuDraftPrAction: (changes: readonly SovereignStagedChange[]) => void;
  sideMenuDraftPrDecision: any;
  sideMenuShareDecision: any;
  effectiveGitHubAccessState: GitHubAccessState;
  handleSideMenuCancelAgent: () => void;
  scopedAgentIsRunning: boolean;
  palStats: { total: number; savings: number } | null;
  handleExportChat: () => Promise<void>;

  openWorkbenchSlot: WorkbenchStatusSlotId | null;
  setOpenWorkbenchSlot: (id: WorkbenchStatusSlotId | null) => void;
  workbenchStatusSlots: WorkbenchStatusSlot[];
  handleOpenDraftPr: (url: string) => void;
}

export function WorkbenchOverlays({
  SideDrawer,
  showRepoExplorer,
  setShowRepoExplorer,
  chatRepoSnapshot,
  handleRepoExplorerFileClick,

  showSideMenu,
  setShowSide,
  handleOpenAllTools,
  handleCompactToolSelect,
  handlePresetActionSelect,
  handleSideMenuDraftPrAction,
  sideMenuDraftPrDecision,
  sideMenuShareDecision,
  effectiveGitHubAccessState,
  handleSideMenuCancelAgent,
  scopedAgentIsRunning,
  palStats,
  handleExportChat,

  openWorkbenchSlot,
  setOpenWorkbenchSlot,
  workbenchStatusSlots,
  handleOpenDraftPr,
}: WorkbenchOverlaysProps): React.ReactElement {
  return (
    <>
      {showRepoExplorer && chatRepoSnapshot && (
        <div
          onClick={() => setShowRepoExplorer(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 80,
            background: "rgba(14,17,22,0.82)",
            backdropFilter: "blur(6px)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxHeight: "78vh",
              overflowY: "auto",
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderBottom: "none",
              borderRadius: "20px 20px 0 0",
              padding: "12px 14px 20px",
            }}
          >
            <RepoTreeExplorer
              snapshot={chatRepoSnapshot}
              onClose={() => setShowRepoExplorer(false)}
              onFileClick={handleRepoExplorerFileClick}
            />
          </div>
        </div>
      )}
      {showSideMenu && (
        <SideDrawer
          onClose={() => setShowSide(false)}
          onOpenAllTools={handleOpenAllTools}
          onOpenRepo={() => handleCompactToolSelect('repo')}
          onOpenRuntimeLogs={() => handleCompactToolSelect('runtime_logs')}
          onOpenGithubAccess={() => handleCompactToolSelect('github_access')}
          onSelectPreset={handlePresetActionSelect}
          onDraftPrAction={handleSideMenuDraftPrAction}
          draftPrDecision={sideMenuDraftPrDecision}
          shareDecision={sideMenuShareDecision}
          chatRepoSnapshot={chatRepoSnapshot}
          githubAccessState={effectiveGitHubAccessState}
          onCancelAgent={handleSideMenuCancelAgent}
          agentIsRunning={scopedAgentIsRunning}
          palStats={palStats}
          onExportChat={handleExportChat}
        />
      )}
      {openWorkbenchSlot && (
        <WorkbenchSlotDrawer
          slot={workbenchStatusSlots.find((s) => s.id === openWorkbenchSlot) ?? workbenchStatusSlots[0]}
          onClose={() => setOpenWorkbenchSlot(null)}
          onOpenDraftPr={handleOpenDraftPr}
        />
      )}
    </>
  );
}
