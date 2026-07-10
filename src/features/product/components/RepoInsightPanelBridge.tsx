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
import type { WorkspaceInspectorRuntimeResult } from '../runtime/workspaceInspectorRuntime';

export interface RepoInsightPanelBridgeProps {
  repoFiles: RepoFile[];
  scanRegistry: ScanFindingRegistry | null;
  workflowReport: WorkflowWatchReport | null;
  solutionPatternStore: SolutionPatternStore | null;
  currentMission: string;
  onSuggestionClick: (suggestion: RepoInsightSuggestion) => void;
  onRecommendedMissionClick?: (mission: string) => void;
}

const INSPECTOR_LAMP_CLASS: Record<'green' | 'yellow' | 'red', string> = {
  green: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100',
  yellow: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  red: 'border-red-500/30 bg-red-500/10 text-red-100',
};

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

type RepoInsightGateState = 'allowed' | 'blocked';

type RepoInsightGateNextAction =
  | 'use_suggestion'
  | 'fix_blocker_first'
  | 'inspect_repo_evidence';

interface RepoInsightGateSnapshot {
  state: RepoInsightGateState;
  reason: string;
  nextAction: RepoInsightGateNextAction;
  evidenceFiles: string[];
}

type GatedRepoInsightSuggestion = RepoInsightSuggestion & {
  readonly gate?: RepoInsightGateSnapshot;
};

function hasRepoEvidence(target: string, repoFiles: RepoFile[]): boolean {
  const normalized = target.trim().replace(/^\/+/, '');
  if (!normalized) return false;
  if (normalized.endsWith('/')) return repoFiles.some((file) => file.path.startsWith(normalized));
  return repoFiles.some((file) => file.path === normalized || file.path.startsWith(`${normalized}/`));
}

function evidenceForSuggestion(suggestion: RepoInsightSuggestion, repoFiles: RepoFile[]): string[] {
  return suggestion.affectedFiles.filter((target) => hasRepoEvidence(target, repoFiles)).slice(0, 5);
}

function gateSuggestion(
  suggestion: RepoInsightSuggestion,
  output: RepoInsightEngineOutput,
  repoFiles: RepoFile[],
): GatedRepoInsightSuggestion {
  const evidenceFiles = evidenceForSuggestion(suggestion, repoFiles);
  const hasHardBlocker = output.blockers.some((blocker) =>
    blocker.type === 'critical-finding' || blocker.type === 'ci-failure' || blocker.type === 'auth',
  );

  if (suggestion.category === 'feature' && hasHardBlocker) {
    return {
      ...suggestion,
      actionLabel: 'Gate prüfen',
      gate: {
        state: 'blocked',
        reason: 'Feature-Vorschlag wartet, bis kritische Repo-/CI-/Auth-Blocker zuerst behoben sind.',
        nextAction: 'fix_blocker_first',
        evidenceFiles,
      },
    };
  }

  if (suggestion.category === 'feature' && evidenceFiles.length === 0) {
    return {
      ...suggestion,
      actionLabel: 'Evidence prüfen',
      gate: {
        state: 'blocked',
        reason: 'Feature-Vorschlag hat keine belegte Datei im geladenen Repo-Snapshot.',
        nextAction: 'inspect_repo_evidence',
        evidenceFiles: [],
      },
    };
  }

  return {
    ...suggestion,
    gate: {
      state: 'allowed',
      reason: 'Vorschlag ist durch Repo-Struktur oder Runtime-Finding belegt.',
      nextAction: 'use_suggestion',
      evidenceFiles,
    },
  };
}

function gateOutput(output: RepoInsightEngineOutput, repoFiles: RepoFile[]): RepoInsightEngineOutput {
  return {
    ...output,
    fixSuggestions: output.fixSuggestions.map((suggestion) => gateSuggestion(suggestion, output, repoFiles)),
    hardeningSuggestions: output.hardeningSuggestions.map((suggestion) => gateSuggestion(suggestion, output, repoFiles)),
    featureSuggestions: output.featureSuggestions.map((suggestion) => gateSuggestion(suggestion, output, repoFiles)),
  };
}

function isGateBlocked(suggestion: RepoInsightSuggestion): boolean {
  return (suggestion as GatedRepoInsightSuggestion).gate?.state === 'blocked';
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

function WorkspaceInspectorStrip({ inspector }: { readonly inspector: WorkspaceInspectorRuntimeResult | null }) {
  const policy = inspector?.policy;
  if (!policy?.hasVisibleSignals) return null;

  return (
    <div
      className={`mb-3 rounded-xl border px-3 py-2 text-xs ${INSPECTOR_LAMP_CLASS[policy.topLamp]}`}
      data-testid="workspace-inspector-strip"
      aria-label="Workspace Inspector Runtime Hinweise"
    >
      <div className="flex items-center justify-between gap-2">
        <strong className="font-mono text-[11px] uppercase tracking-[0.16em]">Workspace Inspector</strong>
        <span className="font-mono text-[10px] opacity-80">{policy.summary}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {policy.signals.slice(0, 3).map((signal) => (
          <span key={signal.id} className="rounded-full border border-current/20 px-2 py-1 font-mono text-[10px] opacity-90">
            {signal.source}: {signal.message}
          </span>
        ))}
      </div>
    </div>
  );
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
    workspaceInspector,
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

  const effectiveOutput = displayOutput(output ? gateOutput(output, repoFiles) : null);

  const handleSuggestionClick = (suggestion: RepoInsightSuggestion) => {
    if (isGateBlocked(suggestion)) return;
    onSuggestionClick({ ...suggestion, whyUseful: suggestionToMission(suggestion) });
  };

  const handleRecommendedMissionClick = () => {
    if (!effectiveOutput?.recommendedMission) return;
    if (onRecommendedMissionClick) {
      onRecommendedMissionClick(effectiveOutput.recommendedMission);
      return;
    }

    const suggestion = firstSuggestion(effectiveOutput);
    if (suggestion && isGateBlocked(suggestion)) return;
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
    <>
      <WorkspaceInspectorStrip inspector={workspaceInspector} />
      <RepoInsightPanel
        output={effectiveOutput}
        isLoading={isLoading}
        onSuggestionClick={handleSuggestionClick}
        onRecommendedMissionClick={handleRecommendedMissionClick}
      />
    </>
  );
}
