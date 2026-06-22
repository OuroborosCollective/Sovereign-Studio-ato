/**
 * Coach Runtime Bridge Hook
 *
 * Extracts coach state derivation from App.tsx for better maintainability.
 * Publishes coach state to window for mobile-operator-coach consumption.
 */

import { useEffect } from 'react';
import { wallClockMs } from '../../../mobile-operator-coach';
import type { SequentialRuntimeState } from '../runtime/sequentialRuntimeGuard';
import { getLatestSovereignHealthReport, type SovereignHealthStatus } from '../runtime/sovereignHealth';
import { getSovereignHealthRuntimeGate } from '../runtime/sovereignFunctionalGuards';

export type CoachLamp = 'green' | 'yellow' | 'red';
export type CoachSource = 'runtime-library' | 'workflow' | 'repair' | 'telemetry' | 'pattern-memory' | 'remote-memory' | 'runtime' | 'repo' | 'dom-fallback' | 'unknown';

export interface CoachRuntimeState {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source: CoachSource;
  tick: number;
  updatedAt: number;
}

export interface RuntimeReadinessGateInput {
  allowed: boolean;
  status: SovereignHealthStatus;
  reason: string;
}

function latestHealthGate(): RuntimeReadinessGateInput | null {
  const report = getLatestSovereignHealthReport();
  if (!report) return null;

  const gate = getSovereignHealthRuntimeGate(report);
  return {
    allowed: gate.allowed,
    status: gate.status,
    reason: gate.reason,
  };
}

function normalizeWorkflowStatus(value?: string): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

function deriveHealthGateCoachState(healthGate: RuntimeReadinessGateInput, now: number): CoachRuntimeState | null {
  if (healthGate.allowed) return null;

  if (healthGate.status === 'red') {
    return {
      lamp: 'red',
      title: 'Health Gate blockiert',
      message: healthGate.reason,
      action: 'Telemetry und Health prüfen',
      thinking: false,
      source: 'telemetry',
      tick: now,
      updatedAt: now,
    };
  }

  return {
    lamp: 'yellow',
    title: 'Health Gate wartet',
    message: healthGate.reason,
    action: 'Readiness prüfen',
    thinking: false,
    source: 'telemetry',
    tick: now,
    updatedAt: now,
  };
}

function deriveWorkflowCoachState(workflowStatus: string, now: number): CoachRuntimeState | null {
  if (workflowStatus === 'red' || workflowStatus === 'failed' || workflowStatus === 'failure' || workflowStatus === 'error') {
    return {
      lamp: 'red',
      title: 'Workflow fehlgeschlagen',
      message: 'Die CI/CD Checks sind fehlgeschlagen.',
      action: 'Repair prüfen',
      thinking: false,
      source: 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  if (workflowStatus === 'pending' || workflowStatus === 'queued' || workflowStatus === 'in_progress' || workflowStatus === 'waiting' || workflowStatus === 'requested') {
    return {
      lamp: 'yellow',
      title: 'Workflow wartet',
      message: 'GitHub Checks laufen oder stehen aus. Der nächste sichere Bereich ist Workflow, nicht Diff.',
      action: 'Workflow prüfen',
      thinking: false,
      source: 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  if (workflowStatus === 'unknown') {
    return {
      lamp: 'yellow',
      title: 'Workflow prüfen',
      message: 'GitHub Checks sind noch nicht eindeutig. Bitte Workflow ansehen statt weiter durch Diff zu springen.',
      action: 'Workflow prüfen',
      thinking: false,
      source: 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  if (workflowStatus === 'green' || workflowStatus === 'success' || workflowStatus === 'completed') {
    return {
      lamp: 'green',
      title: 'Workflow grün',
      message: 'Package erstellt und Workflow erfolgreich.',
      action: 'Fertig prüfen',
      thinking: false,
      source: 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  return null;
}

export function deriveCoachStateFromRuntime(
  sequentialRuntime: SequentialRuntimeState,
  repoReady: boolean,
  hasPackage: boolean,
  workflowStatus?: string,
  isPublishing?: boolean,
  isWatchingWorkflow?: boolean,
  hasActivePatterns?: boolean,
  healthGate?: RuntimeReadinessGateInput,
): CoachRuntimeState {
  const now = wallClockMs();

  if (sequentialRuntime.activeStep) {
    const step = sequentialRuntime.activeStep;
    const stepRecord = sequentialRuntime.steps[step];

    if (stepRecord?.status === 'running') {
      const stepLabels: Record<string, string> = {
        'repo-load': 'Repository wird geladen',
        'package-build': 'Package wird erstellt',
        'diff-load': 'Interne Quellen werden geprüft',
        'draft-pr-publish': 'Draft PR wird erstellt',
        'workflow-watch': 'Workflow wird beobachtet',
        'repair-plan': 'Repair-Plan wird erstellt',
      };

      return {
        lamp: 'green',
        title: stepLabels[step] || `Schritt: ${step}`,
        message: stepRecord.message || 'Prozess läuft...',
        action: 'Bitte warten',
        thinking: true,
        source: 'runtime-library',
        tick: now,
        updatedAt: now,
      };
    }

    if (stepRecord?.status === 'failed') {
      return {
        lamp: 'red',
        title: 'Schritt fehlgeschlagen',
        message: stepRecord.message || 'Ein Prozessschritt ist fehlgeschlagen.',
        action: 'Repair prüfen',
        thinking: false,
        source: 'runtime-library',
        tick: now,
        updatedAt: now,
      };
    }
  }

  if (!repoReady) {
    return {
      lamp: 'yellow',
      title: 'Repository laden',
      message: 'Bitte GitHub-URL eingeben und Repository laden.',
      action: 'Zuerst Repo laden',
      thinking: false,
      source: 'repo',
      tick: now,
      updatedAt: now,
    };
  }

  const resolvedHealthGate = healthGate ?? latestHealthGate();
  const healthGateCoachState = resolvedHealthGate ? deriveHealthGateCoachState(resolvedHealthGate, now) : null;
  if (healthGateCoachState) return healthGateCoachState;

  if (isPublishing) {
    return {
      lamp: 'green',
      title: 'Draft PR wird erstellt',
      message: 'Branch und Commit werden erstellt...',
      action: 'Bitte warten',
      thinking: true,
      source: 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  if (isWatchingWorkflow) {
    return {
      lamp: 'green',
      title: 'Workflow wird beobachtet',
      message: 'CI/CD Checks werden überwacht...',
      action: 'Bitte warten',
      thinking: true,
      source: 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  const workflowCoachState = deriveWorkflowCoachState(normalizeWorkflowStatus(workflowStatus), now);
  if (workflowCoachState) return workflowCoachState;

  if (hasPackage) {
    return {
      lamp: 'green',
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Die Diff-Ansicht ist nur noch intern; ich führe den nächsten GitHub-/Workflow-Schritt weiter.',
      action: 'Workflow prüfen',
      thinking: false,
      source: hasActivePatterns ? 'pattern-memory' : 'workflow',
      tick: now,
      updatedAt: now,
    };
  }

  return {
    lamp: 'green',
    title: 'Bereit für Auftrag',
    message: 'Repository ist geladen. Auftrag eingeben und Package erstellen.',
    action: 'Package bauen',
    thinking: false,
    source: 'runtime-library',
    tick: now,
    updatedAt: now,
  };
}

export interface UseCoachRuntimeBridgeOptions {
  coachState: CoachRuntimeState;
}

export function useCoachRuntimeBridge({ coachState }: UseCoachRuntimeBridgeOptions): void {
  useEffect(() => {
    if (typeof window === 'undefined') return;

    (window as typeof window & { __sovereignRuntimeCoachState?: CoachRuntimeState }).__sovereignRuntimeCoachState = coachState;

    window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
      detail: coachState,
    }));
  }, [coachState]);
}
