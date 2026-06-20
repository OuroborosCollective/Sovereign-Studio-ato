/**
 * Coach Runtime Bridge Hook
 * 
 * Extracts coach state derivation from App.tsx for better maintainability.
 * Publishes coach state to window for mobile-operator-coach consumption.
 */

import { useEffect } from 'react';
import { wallClockMs } from '../../../mobile-operator-coach';
import type { SequentialRuntimeState } from '../runtime/sequentialRuntimeGuard';

// Coach State Types
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

// Leitet Coach-State aus echtem Runtime ab - keine Mocks, keine Stubs
export function deriveCoachStateFromRuntime(
  sequentialRuntime: SequentialRuntimeState,
  repoReady: boolean,
  hasPackage: boolean,
  workflowStatus?: string,
  isPublishing?: boolean,
  isWatchingWorkflow?: boolean,
  hasActivePatterns?: boolean
): CoachRuntimeState {
  const now = wallClockMs();
  
  // 1. Wenn gerade ein Step läuft
  if (sequentialRuntime.activeStep) {
    const step = sequentialRuntime.activeStep;
    const stepRecord = sequentialRuntime.steps[step];
    
    if (stepRecord?.status === 'running') {
      const stepLabels: Record<string, string> = {
        'repo-load': 'Repository wird geladen',
        'package-build': 'Package wird erstellt',
        'diff-load': 'Diff-Quellen werden geladen',
        'draft-pr-publish': 'Draft PR wird erstellt',
        'workflow-watch': 'Workflow wird beobachtet',
        'repair-plan': 'Repair-Plan wird erstellt'
      };
      return {
        lamp: 'green',
        title: stepLabels[step] || `Schritt: ${step}`,
        message: stepRecord.message || 'Prozess läuft...',
        action: 'Bitte warten',
        thinking: true,
        source: 'runtime-library',
        tick: now,
        updatedAt: now
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
        updatedAt: now
      };
    }
  }
  
  // 2. Wenn Repo nicht geladen
  if (!repoReady) {
    return {
      lamp: 'yellow',
      title: 'Repository laden',
      message: 'Bitte GitHub-URL eingeben und Repository laden.',
      action: 'Zuerst Repo laden',
      thinking: false,
      source: 'repo',
      tick: now,
      updatedAt: now
    };
  }
  
  // 3. Wenn Draft PR erstellt wird
  if (isPublishing) {
    return {
      lamp: 'green',
      title: 'Draft PR wird erstellt',
      message: 'Branch und Commit werden erstellt...',
      action: 'Bitte warten',
      thinking: true,
      source: 'workflow',
      tick: now,
      updatedAt: now
    };
  }
  
  // 4. Wenn Workflow beobachtet wird
  if (isWatchingWorkflow) {
    return {
      lamp: 'green',
      title: 'Workflow wird beobachtet',
      message: 'CI/CD Checks werden überwacht...',
      action: 'Bitte warten',
      thinking: true,
      source: 'workflow',
      tick: now,
      updatedAt: now
    };
  }
  
  // 5. Wenn Workflow fehlgeschlagen
  if (workflowStatus === 'red') {
    return {
      lamp: 'red',
      title: 'Workflow fehlgeschlagen',
      message: 'Die CI/CD Checks sind fehlgeschlagen.',
      action: 'Repair prüfen',
      thinking: false,
      source: 'workflow',
      tick: now,
      updatedAt: now
    };
  }
  
  // 6. Wenn Package bereit
  if (hasPackage) {
    if (workflowStatus === 'green') {
      return {
        lamp: 'green',
        title: 'Fertig!',
        message: 'Package erstellt und Workflow erfolgreich.',
        action: 'Diff prüfen',
        thinking: false,
        source: 'runtime-library',
        tick: now,
        updatedAt: now
      };
    }
    return {
      lamp: 'green',
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Weiter mit Diff',
      thinking: false,
      source: 'runtime-library',
      tick: now,
      updatedAt: now
    };
  }
  
  // 7. Default: bereit für Auftrag
  return {
    lamp: 'green',
    title: 'Bereit für Auftrag',
    message: 'Repository ist geladen. Auftrag eingeben und Package erstellen.',
    action: 'Package bauen',
    thinking: false,
    source: 'runtime-library',
    tick: now,
    updatedAt: now
  };
}

export interface UseCoachRuntimeBridgeOptions {
  coachState: CoachRuntimeState;
}

export function useCoachRuntimeBridge({ coachState }: UseCoachRuntimeBridgeOptions): void {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    // Setze globalen Coach-State
    (window as typeof window & { __sovereignRuntimeCoachState?: CoachRuntimeState }).__sovereignRuntimeCoachState = coachState;
    
    // Broadcast Event für Coach-Update
    window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
      detail: coachState
    }));
  }, [coachState]);
}
