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
  // ⚡ Bolt: Fast return on empty inputs to eliminate Map allocation overhead entirely
  if (entries.length === 0) return [];

  // Group entries by scope, avoiding redundant Map set calls
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

  // ⚡ Bolt: Fast native lexicographical sort replacing slow localeCompare and spread array allocations
  const groupEntries = Array.from(groups.entries());
  groupEntries.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));

  const result: EvidenceLineageChain[] = new Array(groupEntries.length);
  for (let g = 0; g < groupEntries.length; g++) {
    const [scope, scopedEntries] = groupEntries[g];
    // In-place sort with fast native string comparison for tie-breaking
    scopedEntries.sort((left, right) => left.at - right.at || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));

    const count = scopedEntries.length;
    const nodes: EvidenceLineageNode[] = new Array(count);
    let sourcesSummary = '';

    // ⚡ Bolt: Single pass node creation and source summary concatenation avoiding redundant .map() and .join()
    for (let i = 0; i < count; i++) {
      const entry = scopedEntries[i];
      nodes[i] = {
        id: entry.id,
        label: entry.message,
        source: entry.source,
        scope,
        at: entry.at,
        parentId: i > 0 ? scopedEntries[i - 1].id : null,
      };
      if (i > 0) {
        sourcesSummary += ' → ' + entry.source;
      } else {
        sourcesSummary = entry.source;
      }
    }

    result[g] = {
      scope,
      nodes,
      summary: `${count} evidence node(s) in ${scope}: ${sourcesSummary}`,
    };
  }

  return result;
}
