/**
 * Pattern Knowledge Card — Issue #447
 * Displays the user's real pattern memory counters.
 * No fake percentages. Only verified patterns count as locally executable.
 * Layout: 393px mobile constraint.
 */

import { useId } from 'react';
import type { PatternMemoryRuntimeCounters } from '../runtime/patternMemoryRuntime';

export interface PatternKnowledgeCardProps {
  readonly counters: PatternMemoryRuntimeCounters;
  readonly onShowDetails?: () => void;
  readonly onUseLocalMode?: () => void;
}

function formatTimestamp(ts: number | null): string {
  if (ts === null) return '—';
  const d = new Date(ts);
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

const SCOPE_DESCRIPTIONS: Record<'lokal' | 'remote' | 'geteilt', string> = {
  lokal: 'Aus dem lokalen Musterbestand',
  remote: 'Aus dem entfernten Musterbestand',
  geteilt: 'Aus geteilten Sovereign-Mustern abgeleitet',
};

function ScopeTag({ scope }: { readonly scope: 'lokal' | 'remote' | 'geteilt' }) {
  const styles: Record<string, string> = {
    lokal: 'bg-slate-700 text-slate-200',
    remote: 'bg-slate-700 text-slate-300',
    geteilt: 'bg-slate-600 text-slate-200',
  };
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-mono ${styles[scope]}`}
      title={SCOPE_DESCRIPTIONS[scope]}
    >
      {scope}
    </span>
  );
}

function StatRow({ label, value }: { readonly label: string; readonly value: string | number }) {
  return (
    <li className="flex items-baseline justify-between gap-2" title={`${label}: ${value}`}>
      <span className="text-slate-400">{label}</span>
      <span className="tabular-nums text-slate-100">{value}</span>
    </li>
  );
}

export function PatternKnowledgeCard({
  counters,
  onShowDetails,
  onUseLocalMode,
}: PatternKnowledgeCardProps) {
  const hasAny = counters.totalStored > 0;
  const headingId = useId();
  const canUseLocal = counters.localExecutableCount > 0;

  return (
    <section
      aria-labelledby={headingId}
      className="w-full max-w-[393px] rounded border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200"
    >
      <h2 id={headingId} className="mb-3 font-bold tracking-tight">
        Dein Sovereign-Wissensstand
      </h2>

      {!hasAny && (
        <p className="text-slate-400 text-xs">
          Noch keine Pattern gespeichert. Patterns entstehen aus erledigter Arbeit.
        </p>
      )}

      {hasAny && (
        <ul role="list" aria-label="Wissensstand-Metriken" className="space-y-1.5">
          <StatRow label="Gespeicherte Patterns" value={counters.totalStored} />
          <StatRow label="Geprüfte lokale Abläufe" value={counters.verifiedCount} />
          <StatRow label="Lokal ausführbare Schritte" value={counters.localExecutableCount} />
          <StatRow label="Häufig genutzte Workflows" value={counters.frequentlyUsedCount} />
          <StatRow
            label="Letzte Wiederverwendung"
            value={formatTimestamp(counters.lastSuccessfulReuseAt)}
          />
        </ul>
      )}

      {hasAny && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-800 pt-3" role="group" aria-label="Musterquellen">
          <span className="text-xs text-slate-500 mr-1">Quelle:</span>
          <ul role="list" aria-label="Aktive Musterquellen" className="inline-flex flex-wrap gap-1.5">
            {counters.localUserCount > 0 && (
              <li>
                <ScopeTag scope="lokal" />
              </li>
            )}
            {counters.remoteUserCount > 0 && (
              <li>
                <ScopeTag scope="remote" />
              </li>
            )}
            {counters.sharedDerivedCount > 0 && (
              <li>
                <ScopeTag scope="geteilt" />
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-800 pt-3">
        {onShowDetails && (
          <button
            type="button"
            onClick={onShowDetails}
            aria-label="Wissensstand-Details ansehen"
            title="Detaillierte Übersicht der gespeicherten Muster anzeigen"
            className="rounded border border-slate-600 bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700 active:bg-slate-600 focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none transition-colors"
          >
            Details ansehen
          </button>
        )}
        {canUseLocal && onUseLocalMode && (
          <button
            type="button"
            onClick={onUseLocalMode}
            aria-label="Lokalen Modus nutzen"
            title="Lokalen Modus für gespeicherte Abläufe aktivieren"
            className="rounded border border-slate-500 bg-slate-700 px-3 py-1 text-xs text-slate-100 hover:bg-slate-600 active:bg-slate-500 focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none transition-colors"
          >
            Lokalen Modus nutzen
          </button>
        )}
      </div>
    </section>
  );
}
