import { describe, expect, it } from 'vitest';
import { evidenceDensity, independentOriginCount, mapPoint, visibleCasesAt, type EvidenceCase } from './evidenceObservatoryModel';

const baseCase: EvidenceCase = {
  schemaVersion: 'sovereign.evidence-case.v1',
  caseId: 'case-1',
  claim: 'Claim',
  verdict: 'UNPROVEN',
  asOf: '2026-08-16T12:00:00Z',
  sources: [
    { id: 's1', observedAt: '2026-08-16T10:00:00Z' },
    { id: 's2', observedAt: '2026-08-16T11:00:00Z' },
  ],
  timeline: [],
  contradictions: [{ id: 'c1', at: '2026-08-16T11:30:00Z' }],
  sourceLineage: { originA: ['s1', 's2'] },
};

describe('Evidence Observatory model', () => {
  it('counts independent provenance origins instead of citations', () => {
    expect(independentOriginCount(baseCase)).toBe(1);
  });

  it('projects longitude and latitude deterministically', () => {
    expect(mapPoint({ sourceId: 's', lat: 0, lon: 0 }, 360, 180)).toEqual({ x: 180, y: 90 });
    expect(mapPoint({ sourceId: 's', lat: 90, lon: -180 }, 360, 180)).toEqual({ x: 0, y: 0 });
  });

  it('builds a density bucket without turning density into truth', () => {
    const density = evidenceDensity([baseCase]);
    expect(density).toEqual([{ at: '2026-08-16', sourceCount: 2, contradictionCount: 1 }]);
  });

  it('filters cases by historical as-of time', () => {
    const future: EvidenceCase = { ...baseCase, caseId: 'future', asOf: '2026-08-18T00:00:00Z' };
    expect(visibleCasesAt([baseCase, future], '2026-08-17T00:00:00Z').map((item) => item.caseId)).toEqual(['case-1']);
  });
});
