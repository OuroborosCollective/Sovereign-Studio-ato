/**
 * Repo Insight Bridge Hook
 *
 * Connects RepoInsightEngine to the coach state system.
 * Publishes insight-based coach states to window for mobile-operator-coach.
 */

import { useCallback, useEffect, useState } from 'react';
import { wallClockMs } from '../../../mobile-operator-coach';
import type { RepoFile } from '../../github/types';
import type { ScanFindingRegistry } from '../runtime/scanFindingRegistry';
import type { WorkflowWatchReport } from '../runtime/workflowWatch';
import type { SolutionPatternStore } from '../runtime/solutionPatternMemory';
import type {
  RepoInsightEngineInput,
  RepoInsightEngineOutput,
} from '../runtime/repoInsightEngine';
import {
  createRepoInsightSuggestions,
  type RepoInsightSuggestion,
} from '../runtime/repoInsightEngine';
import {
  buildWorkspaceInspectorRuntime,
  type WorkspaceInspectorRuntimeResult,
} from '../runtime/workspaceInspectorRuntime';
import type { CoachLamp } from '../hooks/useCoachRuntimeBridge';

const EMPTY_SOLUTION_PATTERN_STORE: SolutionPatternStore = {
  version: 1,
  patterns: [],
  rejections: [],
  updatedAt: 0,
};

export interface RepoInsightBridgeState {
  output: RepoInsightEngineOutput | null;
  workspaceInspector: WorkspaceInspectorRuntimeResult | null;
  isLoading: boolean;
  error: string | null;
  lastAnalyzedFiles: number;
}

export interface UseRepoInsightBridgeOptions {
  repoFiles: RepoFile[];
  repoUrl?: string;
  repoBranch?: string;
  scanRegistry?: ScanFindingRegistry | null;
  workflowReport?: WorkflowWatchReport | null;
  solutionPatternStore?: SolutionPatternStore | null;
  currentMission?: string;
  autoAnalyze?: boolean;
}

export interface UseRepoInsightBridgeResult extends RepoInsightBridgeState {
  analyze: () => void;
  getSuggestionMission: (suggestion: RepoInsightSuggestion) => string;
  coachState: {
    lamp: CoachLamp;
    title: string;
    message: string;
    action: string;
    thinking: boolean;
    source: 'repo' | 'runtime-library';
  } | null;
}

function repoNameFromUrl(repoUrl?: string): string {
  if (!repoUrl) return 'unknown-repo';
  const trimmed = repoUrl.trim().replace(/\.git$/i, '');
  const parts = trimmed.split('/').filter(Boolean);
  return parts.at(-1) ?? 'unknown-repo';
}

function deriveCoachStateFromInsight(
  output: RepoInsightEngineOutput | null,
  isLoading: boolean,
): UseRepoInsightBridgeResult['coachState'] {
  if (isLoading) {
    return {
      lamp: 'green',
      title: 'Repo wird analysiert',
      message: 'Die Repository-Struktur wird ausgewertet...',
      action: 'Bitte warten',
      thinking: true,
      source: 'repo',
    };
  }

  if (!output) {
    return {
      lamp: 'yellow',
      title: 'Keine Analyse verfügbar',
      message: 'Lade ein Repository, um Vorschläge zu erhalten.',
      action: 'Repo laden',
      thinking: false,
      source: 'repo',
    };
  }

  return {
    lamp: output.coachStatus,
    title: output.coachStatus === 'red'
      ? 'Blocker erkannt'
      : output.coachStatus === 'yellow'
        ? 'Vorschläge bereit'
        : 'Analyse abgeschlossen',
    message: output.coachMessage,
    action: output.recommendedMission ? 'Empfohlene Aufgabe ansehen' : 'Vorschläge prüfen',
    thinking: false,
    source: 'repo',
  };
}

export function useRepoInsightBridge(
  options: UseRepoInsightBridgeOptions,
): UseRepoInsightBridgeResult {
  const {
    repoFiles,
    repoUrl,
    repoBranch,
    scanRegistry,
    workflowReport,
    solutionPatternStore,
    currentMission,
    autoAnalyze = true,
  } = options;

  const [state, setState] = useState<RepoInsightBridgeState>({
    output: null,
    workspaceInspector: null,
    isLoading: false,
    error: null,
    lastAnalyzedFiles: 0,
  });

  const analyze = useCallback(() => {
    const inspector = buildWorkspaceInspectorRuntime({
      repoName: repoNameFromUrl(repoUrl),
      branch: repoBranch?.trim() || 'main',
      repoFiles,
      mission: currentMission ?? '',
      repoReady: repoFiles.length > 0,
      blockers: [],
      automationMode: 'manual',
      solutionPatternStore: solutionPatternStore ?? EMPTY_SOLUTION_PATTERN_STORE,
      now: wallClockMs(),
    });

    if (repoFiles.length === 0) {
      setState((prev) => ({
        ...prev,
        workspaceInspector: inspector,
        isLoading: false,
        error: 'No repository files to analyze.',
      }));
      return;
    }

    setState((prev) => ({ ...prev, workspaceInspector: inspector, isLoading: true, error: null }));

    const input: RepoInsightEngineInput = {
      repoFiles,
      repoUrl,
      repoBranch,
      scanRegistry: scanRegistry ?? null,
      workflowReport: workflowReport ?? null,
      telemetry: null,
      solutionPatternStore: solutionPatternStore ?? null,
      currentMission: currentMission ?? '',
    };

    const result = createRepoInsightSuggestions(input);
    const blockers = result.output?.blockers.map((blocker) => blocker.message) ?? [];
    const workspaceInspector = buildWorkspaceInspectorRuntime({
      repoName: repoNameFromUrl(repoUrl),
      branch: repoBranch?.trim() || 'main',
      repoFiles,
      mission: currentMission ?? '',
      repoReady: repoFiles.length > 0,
      blockers,
      automationMode: 'manual',
      solutionPatternStore: solutionPatternStore ?? EMPTY_SOLUTION_PATTERN_STORE,
      now: wallClockMs(),
    });

    setState({
      output: result.output,
      workspaceInspector,
      isLoading: false,
      error: result.error,
      lastAnalyzedFiles: repoFiles.length,
    });
  }, [repoFiles, repoUrl, repoBranch, scanRegistry, workflowReport, solutionPatternStore, currentMission]);

  useEffect(() => {
    if (autoAnalyze && repoFiles.length > 0) analyze();
  }, [autoAnalyze, analyze, repoFiles.length]);

  const coachState = deriveCoachStateFromInsight(state.output, state.isLoading);

  useEffect(() => {
    if (typeof window === 'undefined' || !coachState) return;

    window.dispatchEvent(
      new CustomEvent('sovereign:repo-insight-state', {
        detail: {
          ...coachState,
          workspaceInspector: state.workspaceInspector?.policy ?? null,
          tick: wallClockMs(),
          updatedAt: wallClockMs(),
        },
      }),
    );
  }, [coachState, state.workspaceInspector]);

  const getSuggestionMission = useCallback(
    (suggestion: RepoInsightSuggestion): string => {
      const affectedFiles = suggestion.affectedFiles.slice(0, 5).join(', ') || 'passende Projektdateien';
      return `${suggestion.title}\nBetroffene Dateien/Ordner: ${affectedFiles}\nNutzen: ${suggestion.expectedBenefit}`;
    },
    [],
  );

  return {
    ...state,
    analyze,
    getSuggestionMission,
    coachState,
  };
}
