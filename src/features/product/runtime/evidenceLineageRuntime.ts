export interface EvidenceLineageInput {
  readonly id: string;
  readonly source: string;
  readonly scope: string;
  readonly message: string;
  readonly at: number;
}

export interface EvidenceLineageNode {
  readonly id: string;
  readonly label: string;
  readonly source: string;
  readonly scope: string;
  readonly at: number;
  readonly parentId: string | null;
}

export interface EvidenceLineageChain {
  readonly scope: string;
  readonly nodes: readonly EvidenceLineageNode[];
  readonly summary: string;
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
