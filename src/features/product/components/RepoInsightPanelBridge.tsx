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
import type { RepoInsightEngineOutput, RepoInsightSuggestion } from '../runtime/repoInsightEngine';

export interface RepoInsightPanelBridgeProps {
  repoFiles: RepoFile[];
  scanRegistry: ScanFindingRegistry | null;
  workflowReport: WorkflowWatchReport | null;
  solutionPatternStore: SolutionPatternStore | null;
  currentMission: string;
  onSuggestionClick: (suggestion: RepoInsightSuggestion) => void;
  onRecommendedMissionClick?: (mission: string) => void;
}

function missionVerb(category: RepoInsightSuggestion['category']): string {
  if (category === 'fix') return 'Repariere';
  if (category === 'stabilitaet') return 'Stabilisiere';
  return 'Erweitere';
}

function safeAffectedFiles(files: string[]): string {
  const targets = files.filter(Boolean).slice(0, 5);
  return targets.length > 0 ? targets.join(', ') : 'passende Projektdateien';
}

function suggestionToMission(suggestion: RepoInsightSuggestion): string {
  return [
    `${missionVerb(suggestion.category)}: ${suggestion.title}.`,
    `Betroffene Dateien/Ordner: ${safeAffectedFiles(suggestion.affectedFiles)}.`,
    `Warum sinnvoll: ${suggestion.whyUseful}`,
    `Erwarteter Nutzen: ${suggestion.expectedBenefit}`,
    'Arbeite nur an echten Repo-Dateien und ergaenze passende Tests.',
  ].join('\n');
}

function isPlaceholderMission(mission: string): boolean {
  const value = mission.toLowerCase().replace(/\s+/g, ' ').trim();
  return !value || value === 'readme + update history' || value === 'workflow fehleranalyse + runtime check + test plan' || value === 'fehler' || value === 'ideen' || value === 'plan';
}

function firstSuggestion(output: RepoInsightEngineOutput): RepoInsightSuggestion | null {
  return output.fixSuggestions[0] ?? output.hardeningSuggestions[0] ?? output.featureSuggestions[0] ?? null;
}

function displayOutput(output: RepoInsightEngineOutput | null): RepoInsightEngineOutput | null {
  if (!output || !isPlaceholderMission(output.recommendedMission)) return output;

  const suggestion = firstSuggestion(output);
  if (!suggestion) return output;

  return {
    ...output,
    recommendedMission: suggestionToMission(suggestion),
    recommendedMissionConfidence: Math.max(output.recommendedMissionConfidence, 0.82),
  };
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
    solutionPatternStore,
    currentMission,
    autoAnalyze: true,
  });

  void analyze;
  void coachState;

  const effectiveOutput = displayOutput(output);

  const handleSuggestionClick = (suggestion: RepoInsightSuggestion) => {
    onSuggestionClick({ ...suggestion, whyUseful: suggestionToMission(suggestion) });
  };

  const handleRecommendedMissionClick = () => {
    if (!effectiveOutput?.recommendedMission) return;
    if (onRecommendedMissionClick) {
      onRecommendedMissionClick(effectiveOutput.recommendedMission);
      return;
    }

    const suggestion = firstSuggestion(effectiveOutput);
    onSuggestionClick({
      id: 'insight-recommended-mission',
      category: suggestion?.category ?? 'stabilitaet',
      title: 'Empfohlene nächste Aufgabe',
      whyUseful: effectiveOutput.recommendedMission,
      affectedFiles: suggestion?.affectedFiles ?? ['src/'],
      risk: suggestion?.risk ?? 'mittel',
      expectedBenefit: 'Das Tool setzt die aus der Repo-Analyse abgeleitete nächste Aufgabe um.',
      actionLabel: 'Umsetzen lassen',
      priority: 0,
    });
  };

  return (
    <RepoInsightPanel
      output={effectiveOutput}
      isLoading={isLoading}
      onSuggestionClick={handleSuggestionClick}
      onRecommendedMissionClick={handleRecommendedMissionClick}
    />
  );
}
