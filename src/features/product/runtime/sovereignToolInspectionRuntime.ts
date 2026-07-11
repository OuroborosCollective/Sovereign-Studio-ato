import { create } from 'zustand';

export type SovereignToolInspectionId = 'health' | 'memory' | 'coverage' | 'settings';

export type SovereignToolInspectionOutcome =
  | 'checking'
  | 'ready'
  | 'empty'
  | 'warning'
  | 'failed';

export interface SovereignToolInspectionEvidence {
  readonly outcome: SovereignToolInspectionOutcome;
  readonly statusLabel: string;
  readonly reason: string;
  readonly nextAction: string;
  readonly observedAt: number;
}

export const SOVEREIGN_TOOL_INSPECTION_EVIDENCE_TTL_MS = 60_000;

export function isSovereignToolInspectionEvidenceFresh(
  evidence: SovereignToolInspectionEvidence,
  now = Date.now(),
  ttlMs = SOVEREIGN_TOOL_INSPECTION_EVIDENCE_TTL_MS,
): boolean {
  if (!Number.isFinite(evidence.observedAt) || evidence.observedAt <= 0) return false;
  if (!Number.isFinite(now) || !Number.isFinite(ttlMs) || ttlMs < 0) return false;
  const age = now - evidence.observedAt;
  return age >= 0 && age <= ttlMs;
}

export type SovereignToolInspectionEvidenceMap = Readonly<
  Partial<Record<SovereignToolInspectionId, SovereignToolInspectionEvidence>>
>;

interface SovereignToolInspectionStore {
  readonly evidence: SovereignToolInspectionEvidenceMap;
  readonly recordEvidence: (
    id: SovereignToolInspectionId,
    evidence: SovereignToolInspectionEvidence,
  ) => void;
  readonly clearEvidence: (id: SovereignToolInspectionId) => void;
  readonly resetEvidence: () => void;
}

export const useSovereignToolInspectionStore = create<SovereignToolInspectionStore>((set) => ({
  evidence: {},
  recordEvidence: (id, evidence) => {
    set((current) => ({ evidence: { ...current.evidence, [id]: evidence } }));
  },
  clearEvidence: (id) => {
    set((current) => {
      const next = { ...current.evidence };
      delete next[id];
      return { evidence: next };
    });
  },
  resetEvidence: () => set({ evidence: {} }),
}));

export interface SettingsInspectionInput {
  readonly storageReady: boolean;
  readonly online: boolean;
  readonly language: string;
}

export function deriveSettingsInspectionEvidence(
  input: SettingsInspectionInput,
  observedAt = Date.now(),
): SovereignToolInspectionEvidence {
  const restrictions = [
    !input.storageReady ? 'Browser-Speicher blockiert' : null,
    !input.online ? 'Browser meldet offline' : null,
  ].filter((value): value is string => Boolean(value));

  if (restrictions.length > 0) {
    return {
      outcome: 'warning',
      statusLabel: 'Session eingeschränkt',
      reason: `${restrictions.join(' · ')} · Sprache: ${input.language || 'unknown'}.`,
      nextAction: 'Client- oder Browser-Einstellungen prüfen.',
      observedAt,
    };
  }

  return {
    outcome: 'ready',
    statusLabel: 'Session geprüft',
    reason: `Browser-Speicher verfügbar · Client online · Sprache: ${input.language || 'unknown'}.`,
    nextAction: 'Session-Einstellungen anzeigen oder ändern.',
    observedAt,
  };
}

export interface MemoryInspectionInput {
  readonly storageReady: boolean;
  readonly relevantKeyCount: number;
}

export function deriveMemoryInspectionEvidence(
  input: MemoryInspectionInput,
  observedAt = Date.now(),
): SovereignToolInspectionEvidence {
  if (!input.storageReady) {
    return {
      outcome: 'failed',
      statusLabel: 'Storage blockiert',
      reason: 'Lokaler Browser-Speicher konnte nicht gelesen werden.',
      nextAction: 'Browser-Speicher freigeben und Memory erneut öffnen.',
      observedAt,
    };
  }

  const keyCount = Number.isFinite(input.relevantKeyCount)
    ? Math.max(0, Math.floor(input.relevantKeyCount))
    : 0;

  if (keyCount === 0) {
    return {
      outcome: 'empty',
      statusLabel: 'Keine Memory-Evidence',
      reason: 'Im Browser wurden keine relevanten Memory- oder Pattern-Schlüssel gefunden.',
      nextAction: 'Memory nach einer echten gespeicherten Session erneut prüfen.',
      observedAt,
    };
  }

  return {
    outcome: 'ready',
    statusLabel: `${keyCount} Memory-Hinweise`,
    reason: `${keyCount} relevante lokale Schlüssel wurden gezählt; Namen und Inhalte bleiben verborgen.`,
    nextAction: 'Memory-Inspektion anzeigen.',
    observedAt,
  };
}

export interface HealthInspectionInput {
  readonly online: boolean;
  readonly storageReady: boolean;
  readonly serviceWorkerAvailable: boolean;
}

export function deriveHealthInspectionEvidence(
  input: HealthInspectionInput,
  observedAt = Date.now(),
): SovereignToolInspectionEvidence {
  const restrictions = [
    !input.online ? 'Netzwerk offline' : null,
    !input.storageReady ? 'Browser-Speicher blockiert' : null,
    !input.serviceWorkerAvailable ? 'Service Worker nicht verfügbar' : null,
  ].filter((value): value is string => Boolean(value));

  if (restrictions.length > 0) {
    return {
      outcome: 'warning',
      statusLabel: 'Client eingeschränkt',
      reason: `${restrictions.join(' · ')}. Diese Prüfung umfasst nur den aktuellen Client.`,
      nextAction: 'Betroffene Client-Fähigkeit prüfen; CI, Worker und VPS separat prüfen.',
      observedAt,
    };
  }

  return {
    outcome: 'ready',
    statusLabel: 'Client-Checks bestanden',
    reason: 'Netzwerk, Browser-Speicher und Service-Worker-Fähigkeit sind am aktuellen Client verfügbar.',
    nextAction: 'Für vollständige Gesundheit zusätzlich CI, Worker und VPS prüfen.',
    observedAt,
  };
}

export function createCoverageCheckingEvidence(observedAt = Date.now()): SovereignToolInspectionEvidence {
  return {
    outcome: 'checking',
    statusLabel: 'Coverage wird geprüft',
    reason: 'Die generierte Coverage-Map wird aus dem Deployment-Pfad geladen.',
    nextAction: 'Prüfergebnis abwarten.',
    observedAt,
  };
}

export function deriveCoverageInspectionEvidence(input: {
  readonly ok: boolean;
  readonly fileCount?: number;
  readonly detail?: string;
}, observedAt = Date.now()): SovereignToolInspectionEvidence {
  if (!input.ok) {
    return {
      outcome: 'failed',
      statusLabel: 'Coverage Map fehlt',
      reason: input.detail?.trim() || 'Die generierte Coverage-Map konnte nicht gelesen werden.',
      nextAction: 'Release- oder Coverage-Job prüfen und Map erneut laden.',
      observedAt,
    };
  }

  const fileCount = Number.isFinite(input.fileCount)
    ? Math.max(0, Math.floor(input.fileCount ?? 0))
    : 0;

  if (fileCount === 0) {
    return {
      outcome: 'empty',
      statusLabel: 'Coverage Map leer',
      reason: 'Die Coverage-Map wurde geladen, enthält aber keine erkannten Einträge.',
      nextAction: 'Coverage-Erzeugung prüfen; keinen Prozentwert behaupten.',
      observedAt,
    };
  }

  return {
    outcome: 'ready',
    statusLabel: `${fileCount} Coverage-Einträge`,
    reason: `Die generierte Coverage-Map wurde geladen und enthält ${fileCount} Einträge.`,
    nextAction: 'Coverage-Map anzeigen; Prozentwerte nur aus echten Messdaten berechnen.',
    observedAt,
  };
}
