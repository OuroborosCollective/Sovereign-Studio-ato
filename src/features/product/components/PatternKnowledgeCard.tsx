/**
 * Pattern Knowledge Card — Issue #447
 * Displays the user's real pattern memory counters.
 * No fake percentages. Only verified patterns count as locally executable.
 * Layout: 393px mobile constraint.
 */

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

function ScopeTag({ scope }: { readonly scope: 'lokal' | 'remote' | 'geteilt' }) {
  const styles: Record<string, string> = {
    lokal: 'bg-slate-700 text-slate-200',
    remote: 'bg-slate-700 text-slate-300',
    geteilt: 'bg-slate-600 text-slate-200',
  };
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-mono ${styles[scope]}`}
      title={`Geltungsbereich: ${scope}`}
      aria-label={`Geltungsbereich: ${scope}`}
    >
      {scope}
    </span>
  );
}

function StatRow({ label, value }: { readonly label: string; readonly value: string | number }) {
  return (
    <li
      className="flex items-baseline justify-between gap-2"
      title={`Statistik: ${label} - ${value}`}
    >
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
  const canUseLocal = counters.localExecutableCount > 0;

  return (
    <section
      className="w-full max-w-[393px] rounded border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200"
      aria-labelledby="pattern-knowledge-card-title"
    >
      <h2 id="pattern-knowledge-card-title" className="mb-3 font-bold tracking-tight">
        Dein Sovereign-Wissensstand
      </h2>

      {!hasAny && (
        <p className="text-slate-400 text-xs">
          Noch keine Pattern gespeichert. Patterns entstehen aus erledigter Arbeit.
        </p>
      )}

      {hasAny && (
        <ul role="list" aria-label="Statistiken zum Sovereign-Wissensstand" className="space-y-1.5">
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
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-800 pt-3">
          <span className="text-xs text-slate-500 mr-1">Quelle:</span>
          {counters.localUserCount > 0 && (
            <ScopeTag scope="lokal" />
          )}
          {counters.remoteUserCount > 0 && (
            <ScopeTag scope="remote" />
          )}
          {counters.sharedDerivedCount > 0 && (
            <ScopeTag scope="geteilt" />
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-800 pt-3">
        {onShowDetails && (
          <button
            type="button"
            onClick={onShowDetails}
            aria-label="Details zum Sovereign-Wissensstand ansehen"
            title="Details zum Sovereign-Wissensstand ansehen"
            className="rounded border border-slate-600 bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700 active:bg-slate-600 focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 focus-visible:outline-none"
          >
            Details ansehen
          </button>
        )}
        {canUseLocal && onUseLocalMode && (
          <button
            type="button"
            onClick={onUseLocalMode}
            aria-label="Lokalen Modus für verifizierte Abläufe nutzen"
            title="Lokalen Modus für verifizierte Abläufe nutzen"
            className="rounded border border-slate-500 bg-slate-700 px-3 py-1 text-xs text-slate-100 hover:bg-slate-600 active:bg-slate-500 focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 focus-visible:outline-none"
          >
            Lokalen Modus nutzen
          </button>
        )}
      </div>
    </section>
  );
}
