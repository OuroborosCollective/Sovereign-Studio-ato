import { describe, expect, it, vi, beforeEach } from 'vitest';

interface DependencyNode {
  id: string;
  deps: string[];
  resolved: boolean;
}

function resolveDependencies(nodes: Map<string, DependencyNode>): {
  resolved: string[];
  cycle: string[] | null;
} {
  const resolved: string[] = [];
  const visiting = new Set<string>();

  function visit(id: string, path: string[]): string[] | null {
    if (resolved.includes(id)) return null;
    if (visiting.has(id)) {
      const cycleStart = path.indexOf(id);
      return [...path.slice(cycleStart), id];
    }

    visiting.add(id);
    const node = nodes.get(id);
    if (!node) {
      visiting.delete(id);
      return null;
    }

    for (const dep of node.deps) {
      const cycle = visit(dep, [...path, id]);
      if (cycle) return cycle;
    }

    resolved.push(id);
    visiting.delete(id);
    return null;
  }

  for (const id of nodes.keys()) {
    const cycle = visit(id, []);
    if (cycle) return { resolved, cycle };
  }

  return { resolved, cycle: null };
}

describe('sovereignDependencyLifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('resolves linear dependency chain', () => {
    const nodes = new Map<string, DependencyNode>([
      ['a', { id: 'a', deps: ['b'], resolved: false }],
      ['b', { id: 'b', deps: ['c'], resolved: false }],
      ['c', { id: 'c', deps: [], resolved: false }],
    ]);

    const { resolved, cycle } = resolveDependencies(nodes);
    expect(cycle).toBeNull();
    expect(resolved).toEqual(['c', 'b', 'a']);
  });

  it('detects circular dependency', () => {
    const nodes = new Map<string, DependencyNode>([
      ['a', { id: 'a', deps: ['b'], resolved: false }],
      ['b', { id: 'b', deps: ['c'], resolved: false }],
      ['c', { id: 'c', deps: ['a'], resolved: false }],
    ]);

    const { resolved, cycle } = resolveDependencies(nodes);
    expect(cycle).toEqual(['a', 'b', 'c', 'a']);
    expect(resolved.length).toBeLessThan(3);
  });

  it('resolves diamond dependency pattern', () => {
    const nodes = new Map<string, DependencyNode>([
      ['a', { id: 'a', deps: ['b', 'c'], resolved: false }],
      ['b', { id: 'b', deps: ['d'], resolved: false }],
      ['c', { id: 'c', deps: ['d'], resolved: false }],
      ['d', { id: 'd', deps: [], resolved: false }],
    ]);

    const { resolved, cycle } = resolveDependencies(nodes);
    expect(cycle).toBeNull();
    expect(resolved).toContain('d');
    expect(resolved).toContain('b');
    expect(resolved).toContain('c');
    expect(resolved).toContain('a');
  });

  it('handles independent packages', () => {
    const nodes = new Map<string, DependencyNode>([
      ['pkg-a', { id: 'pkg-a', deps: [], resolved: false }],
      ['pkg-b', { id: 'pkg-b', deps: [], resolved: false }],
      ['pkg-c', { id: 'pkg-c', deps: [], resolved: false }],
    ]);

    const { resolved, cycle } = resolveDependencies(nodes);
    expect(cycle).toBeNull();
    expect(resolved).toHaveLength(3);
  });

  it('handles self-referencing package', () => {
    const nodes = new Map<string, DependencyNode>([
      ['self', { id: 'self', deps: ['self'], resolved: false }],
    ]);

    const { resolved, cycle } = resolveDependencies(nodes);
    expect(cycle).toContain('self');
  });
});