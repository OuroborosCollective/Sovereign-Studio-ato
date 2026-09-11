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

// ⚡ Bolt: Fast native lexicographical string comparison replacing slow, localization-heavy localeCompare
function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function buildEvidenceLineage(entries: readonly EvidenceLineageInput[]): EvidenceLineageChain[] {
  const groups = new Map<string, EvidenceLineageInput[]>();
  for (const entry of entries) {
    const scope = entry.scope.trim() || 'runtime';
    const current = groups.get(scope);
    if (current) {
      current.push(entry);
    } else {
      groups.set(scope, [entry]);
    }
  }

  // ⚡ Bolt: Replace localeCompare with fast native string comparisons (< and >) and consolidate
  // node allocation and summary string generation into a single indexed loop pass.
  return [...groups.entries()]
    .sort(([left], [right]) => compareStrings(left, right))
    .map(([scope, scopedEntries]) => {
      const ordered = [...scopedEntries].sort((left, right) => left.at - right.at || compareStrings(left.id, right.id));
      const len = ordered.length;
      const nodes = new Array<EvidenceLineageNode>(len);
      const sources = new Array<string>(len);

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
