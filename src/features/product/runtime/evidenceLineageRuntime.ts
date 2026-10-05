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
  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const scope = entry.scope.trim() || 'runtime';
    let current = groups.get(scope);
    if (!current) {
      current = [];
      groups.set(scope, current);
    }
    current.push(entry);
  }

  // ⚡ Bolt: Fast native lexicographical string comparison replacing slow localeCompare during scope key sorting
  return [...groups.entries()]
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
    .map(([scope, scopedEntries]) => {
      // ⚡ Bolt: Fast native lexicographical string comparison replacing slow localeCompare for tie-breakers
      const ordered = [...scopedEntries].sort(
        (left, right) => left.at - right.at || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0)
      );
      const nodeCount = ordered.length;
      const nodes: EvidenceLineageNode[] = new Array(nodeCount);
      let sourcesSummary = '';

      for (let index = 0; index < nodeCount; index++) {
        const entry = ordered[index];
        nodes[index] = {
          id: entry.id,
          label: entry.message,
          source: entry.source,
          scope,
          at: entry.at,
          parentId: index > 0 ? ordered[index - 1].id : null,
        };
        if (index > 0) {
          sourcesSummary += ' → ';
        }
        sourcesSummary += entry.source;
      }

      return {
        scope,
        nodes,
        summary: `${nodeCount} evidence node(s) in ${scope}: ${sourcesSummary}`,
      };
    });
}
