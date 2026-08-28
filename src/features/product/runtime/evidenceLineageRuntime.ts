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

  // ⚡ Bolt: Fast native lexicographical string comparison replacing slow localeCompare,
  // and single-pass accumulation for nodes and source chain summaries to minimize allocations.
  return [...groups.entries()]
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
    .map(([scope, scopedEntries]) => {
      const ordered = [...scopedEntries].sort(
        (left, right) =>
          left.at - right.at || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0),
      );
      const len = ordered.length;
      const nodes: EvidenceLineageNode[] = new Array(len);
      const sources: string[] = new Array(len);

      for (let i = 0; i < len; i++) {
        const entry = ordered[i];
        nodes[i] = {
          id: entry.id,
          label: entry.message,
          source: entry.source,
          scope,
          at: entry.at,
          parentId: i > 0 ? ordered[i - 1].id : null,
        };
        sources[i] = entry.source;
      }

      return {
        scope,
        nodes,
        summary: `${len} evidence node(s) in ${scope}: ${sources.join(' → ')}`,
      };
    });
}
