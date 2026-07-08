import React, { useEffect } from 'react';
import type { SolutionPatternStore } from '../runtime/solutionPatternMemory';
import { derivePatternMemoryContainerState, canClearPatternMemory } from '../runtime/patternMemoryContainerRuntime';
import {
  createSovereignDependencyLifecycleState,
  recordSovereignDependencyFailure,
  recordSovereignDependencySuccess,
} from '../runtime/sovereignDependencyLifecycle';
import { publishSovereignDependencyCoachSignal } from '../runtime/sovereignDependencyCoachBridge';

export interface PatternMemoryContainerProps {
  store: SolutionPatternStore;
  onClear: () => void;
}

export function PatternMemoryContainer({ store, onClear }: PatternMemoryContainerProps) {
  const state = derivePatternMemoryContainerState(store);
  const safePatterns = Array.isArray(store.patterns) ? store.patterns : [];
  const patterns = safePatterns.filter((pattern) => pattern.status === 'active').slice(0, 20);

  // Track pattern IDs for stable dependency array
  const patternIds = safePatterns.map((p) => p.id).join(',');

  useEffect(() => {
    const dependency = createSovereignDependencyLifecycleState(
      'pattern-memory-store',
      'pattern-memory',
      'Pattern Memory has not been checked yet.',
    );

    const next = Array.isArray(store.patterns)
      ? recordSovereignDependencySuccess(
        dependency,
        patterns.length > 0 ? `${patterns.length} active pattern(s) available.` : 'Pattern Memory is available but empty.',
      ).state
      : recordSovereignDependencyFailure(dependency, {}, 'Pattern Memory store is not readable.').state;

    publishSovereignDependencyCoachSignal(next);
  }, [patterns.length, patternIds, store.patterns]);

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200" data-testid="pattern-memory-container">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Pattern Memory</h2>
          <p className="mt-1 text-xs text-slate-400">{state.summary}</p>
        </div>
        <button type="button" onClick={onClear} disabled={!canClearPatternMemory(store)}>Clear Pattern Memory</button>
      </div>

      <div className="mt-3 grid gap-2 text-xs md:grid-cols-4">
        <div className="rounded bg-slate-900/70 p-2">Active: {state.activePatterns}</div>
        <div className="rounded bg-slate-900/70 p-2">Completed: {state.completedPatterns}</div>
        <div className="rounded bg-slate-900/70 p-2">Reported: {state.reportedPatterns}</div>
        <div className="rounded bg-slate-900/70 p-2">Hits: {state.totalHits}</div>
      </div>

      {patterns.length ? (
        <div className="mt-4 grid gap-3">
          {patterns.map((pattern) => (
            <article key={pattern.id} className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-bold text-slate-100">{pattern.category} {pattern.fileExtension}</h3>
                <span className="text-xs text-slate-400">{pattern.confidence} · hits {pattern.hits}</span>
              </div>
              <p className="mt-2 text-xs text-slate-300">{pattern.problemSummary}</p>
              <p className="mt-1 text-xs text-emerald-200">{pattern.solutionSummary}</p>
              <p className="mt-2 text-[11px] text-slate-500">Nodes: {pattern.intakeNode} → {pattern.processingNode} → {pattern.outputNodes.join(', ')}</p>
              {pattern.tags.length ? <p className="mt-1 text-[11px] text-slate-500">Tags: {pattern.tags.join(', ')}</p> : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-500">No local patterns learned yet.</p>
      )}
    </section>
  );
}
