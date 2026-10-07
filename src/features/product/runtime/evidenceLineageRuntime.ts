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

  // ⚡ Bolt: Fast native lexicographical string comparison replacing slow localeCompare,
  // and single-pass loop mapping to eliminate redundant array allocations and Map entries spreading.
  const sortedScopes = Array.from(groups.keys()).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const result: EvidenceLineageChain[] = new Array(sortedScopes.length);

  for (let i = 0; i < sortedScopes.length; i++) {
    const scope = sortedScopes[i];
    const scopedEntries = groups.get(scope)!;
    scopedEntries.sort(
      (left, right) => left.at - right.at || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0),
    );

    const count = scopedEntries.length;
    const nodes: EvidenceLineageNode[] = new Array(count);
    const sources: string[] = new Array(count);

    for (let j = 0; j < count; j++) {
      const entry = scopedEntries[j];
      nodes[j] = {
        id: entry.id,
        label: entry.message,
        source: entry.source,
        scope,
        at: entry.at,
        parentId: j > 0 ? scopedEntries[j - 1].id : null,
      };
      sources[j] = entry.source;
    }

    result[i] = {
      scope,
      nodes,
      summary: `${count} evidence node(s) in ${scope}: ${sources.join(' → ')}`,
    };
  }

  return result;
}
