/**
 * Runtime Diagnostics – Dependency Graph, Root Cause Analysis & Fix Memory
 *
 * First minimal iteration. Provides:
 *  - createDependencyGraph / findRootCause
 *  - lightweight in‑process fix memory (rememberFix / findPreviousFix)
 *
 * All functions are synchronous and have **zero** external dependencies so
 * they can run inside Node, the browser, or React Native.
 */

export interface DependencyEdge {
  /** source node identifier */
  from: string;
  /** target node identifier (depends on source) */
  to: string;
}

export interface DependencyGraph {
  addEdge(edge: DependencyEdge): void;
  getUpstream(node: string): string[];
  getDownstream(node: string): string[];
  toEdges(): DependencyEdge[];
}

export function createDependencyGraph(edges: DependencyEdge[] = []): DependencyGraph {
  const upstream = new Map<string, Set<string>>();
  const downstream = new Map<string, Set<string>>();

  const ensure = (map: Map<string, Set<string>>, key: string) => {
    if (!map.has(key)) map.set(key, new Set<string>());
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    return map.get(key)!;
  };

  const addEdge = (edge: DependencyEdge) => {
    ensure(downstream, edge.from).add(edge.to);
    ensure(upstream, edge.to).add(edge.from);
    // also ensure nodes exist the other side so lookups never return undefined
    ensure(downstream, edge.to);
    ensure(upstream, edge.from);
  };

  edges.forEach(addEdge);

  return {
    addEdge,
    getUpstream(node) {
      return [...(upstream.get(node) ?? [])];
    },
    getDownstream(node) {
      return [...(downstream.get(node) ?? [])];
    },
    toEdges() {
      const result: DependencyEdge[] = [];
      for (const [from, tos] of downstream) {
        for (const to of tos) result.push({ from, to });
      }
      return result;
    },
  };
}

export interface RootCauseReport {
  /** Root cause node (a node without upstream parents) */
  cause: string;
  /** Path from cause → failing node (reversed order) */
  path: string[];
  /** Heuristic confidence [0‑1] */
  confidence: number;
}

/**
 * Very small BFS‑based root‑cause finder.
 * Walks upstream until a node with no parents is hit.
 */
export function findRootCause(graph: DependencyGraph, failureNode: string): RootCauseReport {
  const visited = new Set<string>();
  const queue: Array<[string, string[]]> = [[failureNode, [failureNode]]];

  while (queue.length) {
    const [node, path] = queue.shift()!;
    if (visited.has(node)) continue;
    visited.add(node);

    const parents = graph.getUpstream(node);
    if (parents.length === 0) {
      return { cause: node, path, confidence: 1 - 1 / (path.length + 1) };
    }

    parents.forEach((p) => queue.push([p, [p, ...path]]));
  }

  // cyclic graph or disconnected – fall back to failure node itself
  return { cause: failureNode, path: [failureNode], confidence: 0.2 };
}

/**
 * -------  FIX MEMORY  -------------------------------------------------------
 * Stores a bounded LRU list of <problem,cause,commit> tuples so previous fixes
 * can be reused in the future (auto‑root‑cause / auto‑repair).
 */

export interface FixMemoryEntry {
  problem: string;
  cause: string;
  patchCommitSha: string;
  timestamp: number; // epoch ms
}

const MAX_ENTRIES = 100;
const memory: FixMemoryEntry[] = [];

export function rememberFix(entry: FixMemoryEntry) {
  memory.unshift(entry);
  if (memory.length > MAX_ENTRIES) memory.pop();
}

export function findPreviousFix(problem: string): FixMemoryEntry | undefined {
  return memory.find((e) => e.problem === problem);
}

export function getAllFixes(): FixMemoryEntry[] {
  return [...memory];
}
