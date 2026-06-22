/**
 * RepoInsightPanelBridge
 *
 * Wraps RepoInsightPanel with the useRepoInsightBridge hook.
 * Provides seamless integration with the main App.
 */

import React from 'react';
import { RepoInsightPanel } from './RepoInsightPanel';
import { useRepoInsightBridge } from '../hooks/useRepoInsightBridge';
import type { RepoFile } from '../../github/types';
import type { ScanFindingRegistry } from '../runtime/scanFindingRegistry';
import type { WorkflowWatchReport } from '../runtime/workflowWatch';
import type { SolutionPatternStore } from '../runtime/solutionPatternMemory';
import type { RepoInsightSuggestion } from '../runtime/repoInsightEngine';

export interface RepoInsightPanelBridgeProps {
  repoFiles: RepoFile[];
  scanRegistry: ScanFindingRegistry | null;
  workflowReport: WorkflowWatchReport | null;
  solutionPatternStore: SolutionPatternStore | null;
  currentMission: string;
  onSuggestionClick: (suggestion: RepoInsightSuggestion) => void;
  onRecommendedMissionClick?: (mission: string) => void;
}

export function RepoInsightPanelBridge({
  repoFiles,
  scanRegistry,
  workflowReport,
  solutionPatternStore,
  currentMission,
  onSuggestionClick,
  onRecommendedMissionClick,
}: RepoInsightPanelBridgeProps) {
  const {
    output,
    isLoading,
    analyze,
    coachState,
  } = useRepoInsightBridge({
    repoFiles,
    scanRegistry,
    workflowReport,
    currentMission,
    autoAnalyze: true,
  });

  const handleSuggestionClick = (suggestion: RepoInsightSuggestion) => {
    onSuggestionClick(suggestion);
  };

  const handleRecommendedMissionClick = () => {
    if (output?.recommendedMission && onRecommendedMissionClick) {
      onRecommendedMissionClick(output.recommendedMission);
    }
  };

  return (
    <RepoInsightPanel
      output={output}
      isLoading={isLoading}
      onSuggestionClick={handleSuggestionClick}
      onRecommendedMissionClick={handleRecommendedMissionClick}
    />
  );
}
