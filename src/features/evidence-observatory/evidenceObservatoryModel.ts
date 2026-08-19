export type EvidenceVerdict = 'SUPPORTED' | 'REFUTED' | 'UNPROVEN' | 'NOT_APPLICABLE';

export type EvidenceSource = {
  id: string;
  label?: string;
  sourceType?: string;
  locator?: string;
  observedAt?: string;
  excerpt?: string;
  contentSha256?: string;
  provenance?: { originFamily?: string; [key: string]: unknown };
  geo?: { lat?: number; lon?: number; evidenceRole?: 'material' | 'context'; label?: string };
};

export type EvidenceTimelineEvent = {
  id?: string;
  at: string;
  title?: string;
  summary?: string;
  sourceIds?: string[];
};

export type MaterialGeoEvidence = {
  sourceId: string;
  label?: string;
  lat: number;
  lon: number;
};

export type EvidenceCase = {
  schemaVersion: string;
  caseId: string;
  projectId?: string;
  title?: string;
  claim: string;
  claimSha256?: string;
  verdict: EvidenceVerdict;
  evidenceClass?: string;
  workflowState?: string;
  asOf?: string;
  caseSha256?: string;
  sources: EvidenceSource[];
  timeline: EvidenceTimelineEvent[];
  contradictions?: Array<{ id?: string; summary?: string; [key: string]: unknown }>;
  evidenceNeeded?: string[];
  verdictBasis?: { sourceIds?: string[]; proofReceiptIds?: string[] };
  sourceLineage?: Record<string, string[]>;
  materialGeoEvidence?: MaterialGeoEvidence[];
  claimGenealogy?: Array<{ id?: string; fromSourceId?: string; toSourceId?: string; mutation?: string; [key: string]: unknown }>;
  informationFlow?: Array<{ id?: string; fromSourceId?: string; toSourceId?: string; relation?: string; [key: string]: unknown }>;
  gateReport?: Record<string, unknown>;
  evidencePassport?: Record<string, unknown>;
  passportSha256?: string;
};

export type AtlasResponse = {
  ok: boolean;
  cases: EvidenceCase[];
  count: number;
  sourceCount: number;
  materialGeoEvidenceCount: number;
  asOf?: string | null;
  projectId?: string | null;
  truthNotice?: string;
};

export type ArenaMetricSummary = {
  overallScore: number;
  evidenceAdherence: number;
  citationPrecision: number;
  unsupportedClaimRate: number;
  correctAbstentionRate?: number;
};

export type ArenaLeaderboardEntry = ArenaMetricSummary & {
  modelId: string;
  provider: string;
  runs: number;
};

export type SourceDependencyAnalysis = {
  schemaVersion: string;
  sourceId: string;
  sourceSha256?: string;
  removedOriginFamily?: string | null;
  originStillRepresented: boolean;
  remainingSourceCount: number;
  remainingIndependentOriginCount: number;
  verdictBasisSourceRemoved: boolean;
  dependentProofReceiptIds: string[];
  verdictBasisReceiptDependencyBroken: boolean;
  timelineEventsAffected: number;
  simulationOnly: true;
  verdictRecomputed: false;
  analysisSha256: string;
  truthNotice: string;
};

export type DensityBucket = {
  at: string;
  sourceCount: number;
  contradictionCount: number;
};

export function verdictTone(verdict: EvidenceVerdict): string {
  if (verdict === 'SUPPORTED') return 'supported';
  if (verdict === 'REFUTED') return 'refuted';
  if (verdict === 'NOT_APPLICABLE') return 'not-applicable';
  return 'unproven';
}

export function evidenceDensity(cases: EvidenceCase[]): DensityBucket[] {
  const buckets = new Map<string, DensityBucket>();
  for (const item of cases) {
    for (const source of item.sources || []) {
      if (!source.observedAt) continue;
      const at = source.observedAt.slice(0, 10);
      const current = buckets.get(at) || { at, sourceCount: 0, contradictionCount: 0 };
      current.sourceCount += 1;
      buckets.set(at, current);
    }
    for (const contradiction of item.contradictions || []) {
      const at = String((contradiction as Record<string, unknown>).at || item.asOf || '').slice(0, 10);
      if (!at) continue;
      const current = buckets.get(at) || { at, sourceCount: 0, contradictionCount: 0 };
      current.contradictionCount += 1;
      buckets.set(at, current);
    }
  }
  // Optimized by replacing slow localeCompare with native lexicographical comparison operators (< and >)
  // for ISO date string sorting ('YYYY-MM-DD'). Up to 10-20x faster in V8 string comparison callbacks.
  return [...buckets.values()].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}

export function independentOriginCount(item: EvidenceCase): number {
  return Object.keys(item.sourceLineage || {}).length;
}

export function mapPoint(point: MaterialGeoEvidence, width: number, height: number) {
  const x = ((Number(point.lon) + 180) / 360) * width;
  const y = ((90 - Number(point.lat)) / 180) * height;
  return {
    x: Math.max(0, Math.min(width, x)),
    y: Math.max(0, Math.min(height, y)),
  };
}

export function visibleCasesAt(cases: EvidenceCase[], asOf?: string): EvidenceCase[] {
  if (!asOf) return cases;
  const boundary = Date.parse(asOf);
  if (!Number.isFinite(boundary)) return cases;
  return cases.filter((item) => {
    if (!item.asOf) return true;
    const value = Date.parse(item.asOf);
    return !Number.isFinite(value) || value <= boundary;
  });
}
