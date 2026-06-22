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
import type {
  RepoInsightEngineInput,
  RepoInsightEngineOutput,
} from '../runtime/repoInsightEngine';
import {
  createRepoInsightSuggestions,
  type RepoInsightSuggestion,
} from '../runtime/repoInsightEngine';
import type { CoachLamp } from '../hooks/useCoachRuntimeBridge';

export interface RepoInsightBridgeState {
  output: RepoInsightEngineOutput | null;
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
  solutionPatternStore?: unknown | null;
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

function deriveCoachStateFromInsight(
  output: RepoInsightEngineOutput | null,
  isLoading: boolean,
): UseRepoInsightBridgeResult['coachState'] {
  const now = wallClockMs();

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
    action: output.recommendedMission
      ? 'Empfohlene Aufgabe ansehen'
      : 'Vorschläge prüfen',
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
    currentMission,
    autoAnalyze = true,
  } = options;

  const [state, setState] = useState<RepoInsightBridgeState>({
    output: null,
    isLoading: false,
    error: null,
    lastAnalyzedFiles: 0,
  });

  const analyze = useCallback(() => {
    if (repoFiles.length === 0) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: 'No repository files to analyze.',
      }));
      return;
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    const input: RepoInsightEngineInput = {
      repoFiles,
      repoUrl,
      repoBranch,
      scanRegistry: scanRegistry ?? null,
      workflowReport: workflowReport ?? null,
      telemetry: null,
      solutionPatternStore: null,
      currentMission: currentMission ?? '',
    };

    // Run analysis synchronously (it's fast)
    const result = createRepoInsightSuggestions(input);

    setState({
      output: result.output,
      isLoading: false,
      error: result.error,
      lastAnalyzedFiles: repoFiles.length,
    });
  }, [repoFiles, repoUrl, repoBranch, scanRegistry, workflowReport, currentMission]);

  // Auto-analyze when inputs change
  useEffect(() => {
    if (autoAnalyze && repoFiles.length > 0) {
      analyze();
    }
  }, [autoAnalyze, analyze, repoFiles.length]);

  // Publish coach state to window
  const coachState = deriveCoachStateFromInsight(state.output, state.isLoading);

  useEffect(() => {
    if (typeof window === 'undefined' || !coachState) return;

    window.dispatchEvent(
      new CustomEvent('sovereign:repo-insight-state', {
        detail: {
          ...coachState,
          tick: wallClockMs(),
          updatedAt: wallClockMs(),
        },
      }),
    );
  }, [coachState]);

  const getSuggestionMission = useCallback(
    (suggestion: RepoInsightSuggestion): string => {
      const affectedFiles = suggestion.affectedFiles.slice(0, 2).join(', ');
      return `${suggestion.title} in ${affectedFiles}`;
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
