import { beforeEach, describe, expect, it } from 'vitest';
import {
  createCoverageCheckingEvidence,
  deriveCoverageInspectionEvidence,
  deriveHealthInspectionEvidence,
  deriveMemoryInspectionEvidence,
  deriveSettingsInspectionEvidence,
  isSovereignToolInspectionEvidenceFresh,
  SOVEREIGN_TOOL_INSPECTION_EVIDENCE_TTL_MS,
  useSovereignToolInspectionStore,
} from './sovereignToolInspectionRuntime';

beforeEach(() => {
  useSovereignToolInspectionStore.getState().resetEvidence();
});

describe('sovereignToolInspectionRuntime', () => {
  it('stores and clears evidence without fabricating defaults', () => {
    expect(useSovereignToolInspectionStore.getState().evidence).toEqual({});
    const evidence = deriveHealthInspectionEvidence({
      online: true,
      storageReady: true,
      serviceWorkerAvailable: true,
    });
    useSovereignToolInspectionStore.getState().recordEvidence('health', evidence);
    expect(useSovereignToolInspectionStore.getState().evidence.health).toEqual(evidence);
    useSovereignToolInspectionStore.getState().clearEvidence('health');
    expect(useSovereignToolInspectionStore.getState().evidence.health).toBeUndefined();
  });

  it('expires inspection evidence instead of trusting old UI status indefinitely', () => {
    const observedAt = 10_000;
    const evidence = deriveHealthInspectionEvidence({
      online: true,
      storageReady: true,
      serviceWorkerAvailable: true,
    }, observedAt);

    expect(isSovereignToolInspectionEvidenceFresh(
      evidence,
      observedAt + SOVEREIGN_TOOL_INSPECTION_EVIDENCE_TTL_MS,
    )).toBe(true);
    expect(isSovereignToolInspectionEvidenceFresh(
      evidence,
      observedAt + SOVEREIGN_TOOL_INSPECTION_EVIDENCE_TTL_MS + 1,
    )).toBe(false);
    expect(isSovereignToolInspectionEvidenceFresh({ ...evidence, observedAt: 0 }, observedAt)).toBe(false);
  });

  it('keeps health truth scoped to client checks', () => {
    expect(deriveHealthInspectionEvidence({
      online: true,
      storageReady: true,
      serviceWorkerAvailable: true,
    })).toMatchObject({ outcome: 'ready', statusLabel: 'Client-Checks bestanden' });

    const restricted = deriveHealthInspectionEvidence({
      online: false,
      storageReady: true,
      serviceWorkerAvailable: false,
    });
    expect(restricted).toMatchObject({ outcome: 'warning', statusLabel: 'Client eingeschränkt' });
    expect(restricted.reason).toContain('nur den aktuellen Client');
  });

  it('counts memory evidence without exposing key names or values', () => {
    expect(deriveMemoryInspectionEvidence({ storageReady: true, relevantKeyCount: 0 }))
      .toMatchObject({ outcome: 'empty', statusLabel: 'Keine Memory-Evidence' });

    const evidence = deriveMemoryInspectionEvidence({ storageReady: true, relevantKeyCount: 4 });
    expect(evidence).toMatchObject({ outcome: 'ready', statusLabel: '4 Memory-Hinweise' });
    expect(evidence.reason).toContain('Namen und Inhalte bleiben verborgen');
  });

  it('records settings restrictions instead of claiming persistence success', () => {
    expect(deriveSettingsInspectionEvidence({ storageReady: true, online: true, language: 'de-DE' }))
      .toMatchObject({ outcome: 'ready', statusLabel: 'Session geprüft' });
    expect(deriveSettingsInspectionEvidence({ storageReady: false, online: false, language: 'de-DE' }))
      .toMatchObject({ outcome: 'warning', statusLabel: 'Session eingeschränkt' });
  });

  it('distinguishes coverage checking, missing, empty and real entries', () => {
    expect(createCoverageCheckingEvidence()).toMatchObject({ outcome: 'checking' });
    expect(deriveCoverageInspectionEvidence({ ok: false, detail: 'HTTP 404' }))
      .toMatchObject({ outcome: 'failed', statusLabel: 'Coverage Map fehlt' });
    expect(deriveCoverageInspectionEvidence({ ok: true, fileCount: 0 }))
      .toMatchObject({ outcome: 'empty', statusLabel: 'Coverage Map leer' });
    expect(deriveCoverageInspectionEvidence({ ok: true, fileCount: 12 }))
      .toMatchObject({ outcome: 'ready', statusLabel: '12 Coverage-Einträge' });
  });
});
