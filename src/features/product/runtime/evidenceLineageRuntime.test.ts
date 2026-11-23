import { describe, expect, it } from 'vitest';
import { buildEvidenceLineage, type EvidenceLineageInput } from './evidenceLineageRuntime';

describe('evidenceLineageRuntime', () => {
  it('handles empty input array immediately', () => {
    expect(buildEvidenceLineage([])).toEqual([]);
  });

  it('groups, sorts scopes, and establishes parentId relationships deterministically', () => {
    const entries: EvidenceLineageInput[] = [
      { id: 'ev-3', source: 'worker', scope: 'draft-pr', message: 'applied diff', at: 300 },
      { id: 'ev-1', source: 'user', scope: 'draft-pr', message: 'initiated plan', at: 100 },
      { id: 'ev-2', source: 'llm', scope: 'draft-pr', message: 'generated code', at: 200 },
      { id: 'ev-0', source: 'monitor', scope: 'analytics', message: 'session open', at: 50 },
    ];

    const result = buildEvidenceLineage(entries);

    expect(result).toHaveLength(2);

    // Lexicographical scope sorting: 'analytics' before 'draft-pr'
    expect(result[0].scope).toBe('analytics');
    expect(result[0].summary).toBe('1 evidence node(s) in analytics: monitor');
    expect(result[0].nodes).toHaveLength(1);
    expect(result[0].nodes[0]).toEqual({
      id: 'ev-0',
      label: 'session open',
      source: 'monitor',
      scope: 'analytics',
      at: 50,
      parentId: null,
    });

    expect(result[1].scope).toBe('draft-pr');
    expect(result[1].summary).toBe('3 evidence node(s) in draft-pr: user → llm → worker');
    expect(result[1].nodes.map((n) => n.id)).toEqual(['ev-1', 'ev-2', 'ev-3']);
    expect(result[1].nodes[0].parentId).toBeNull();
    expect(result[1].nodes[1].parentId).toBe('ev-1');
    expect(result[1].nodes[2].parentId).toBe('ev-2');
  });

  it('defaults blank or whitespace-only scope to runtime', () => {
    const entries: EvidenceLineageInput[] = [
      { id: 'ev-1', source: 'kernel', scope: '   ', message: 'boot', at: 10 },
      { id: 'ev-2', source: 'agent', scope: '', message: 'ready', at: 20 },
    ];

    const result = buildEvidenceLineage(entries);
    expect(result).toHaveLength(1);
    expect(result[0].scope).toBe('runtime');
    expect(result[0].nodes).toHaveLength(2);
    expect(result[0].summary).toBe('2 evidence node(s) in runtime: kernel → agent');
  });

  it('uses tie-breaking by id when timestamps are identical', () => {
    const entries: EvidenceLineageInput[] = [
      { id: 'b', source: 'srcB', scope: 'test', message: 'msgB', at: 100 },
      { id: 'a', source: 'srcA', scope: 'test', message: 'msgA', at: 100 },
      { id: 'c', source: 'srcC', scope: 'test', message: 'msgC', at: 100 },
    ];

    const result = buildEvidenceLineage(entries);
    expect(result[0].nodes.map((n) => n.id)).toEqual(['a', 'b', 'c']);
    expect(result[0].summary).toBe('3 evidence node(s) in test: srcA → srcB → srcC');
  });
});
