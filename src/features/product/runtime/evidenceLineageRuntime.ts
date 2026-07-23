export interface EvidenceLineageInput {
  id: string;
  source: string;
  scope: string;
  message: string;
  at: number;
}

export interface EvidenceLineageNode {
  id: string;
  label: string;
  source: string;
  scope: string;
  at: number;
  parentId: string | null;
}

export interface EvidenceLineageChain {
  scope: string;
  nodes: EvidenceLineageNode[];
  summary: string;
}

export function buildEvidenceLineage(entries: readonly EvidenceLineageInput[]): EvidenceLineageChain[] {
  const groups = new Map<string, EvidenceLineageInput[]>();
  for (const entry of entries) {
    const scope = entry.scope.trim() || 'runtime';
    const current = groups.get(scope) ?? [];
    current.push(entry);
    groups.set(scope, current);
  }

  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([scope, scopedEntries]) => {
      const ordered = [...scopedEntries].sort((left, right) => left.at - right.at || left.id.localeCompare(right.id));
      const nodes = ordered.map((entry, index): EvidenceLineageNode => ({
        id: entry.id,
        label: entry.message,
        source: entry.source,
        scope,
        at: entry.at,
        parentId: index > 0 ? ordered[index - 1].id : null,
      }));
      return {
        scope,
        nodes,
        summary: `${nodes.length} evidence node(s) in ${scope}: ${nodes.map((node) => node.source).join(' → ')}`,
      };
    });
}
