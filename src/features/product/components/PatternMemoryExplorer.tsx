/**
 * Pattern Memory Explorer — Issue #447
 * Detailed list view of learned pattern entries.
 * Shows honest runtime data: no fake counters, no mocked state.
 * Layout: 393px mobile constraint.
 */

import type { LearnedPatternEntry, PatternOwnerScope } from '../runtime/patternMemoryRuntime';

export interface PatternMemoryExplorerProps {
  readonly entries: LearnedPatternEntry[];
  readonly isBusy?: boolean;
  readonly onSelectEntry?: (entryId: string) => void;
  readonly onEraseUserData?: () => void;
  readonly eraseConfirmationText?: string;
  readonly onEraseConfirmationTextChange?: (value: string) => void;
}

const ERASE_CONFIRMATION = 'MEINE DATEN LÖSCHEN';

const SCOPE_LABELS: Record<PatternOwnerScope, string> = {
  'local-user': 'lokal',
  'remote-user': 'remote',
  'shared-derived': 'geteilt',
};

function LampDot({ verified, localExecutable }: { readonly verified: boolean; readonly localExecutable: boolean }) {
  const color = localExecutable
    ? 'bg-green-500'
    : verified
    ? 'bg-yellow-400'
    : 'bg-slate-500';
  const title = localExecutable
    ? 'Geprüft · Lokal ausführbar'
    : verified
    ? 'Geprüft · Nicht lokal ausführbar'
    : 'Nicht geprüft';
  return (
    <span
      title={title}
      className={`inline-block h-2 w-2 flex-shrink-0 rounded-full mt-1 ${color}`}
      aria-label={title}
    />
  );
}

function PatternEntryRow({
  entry,
  onSelect,
}: {
  readonly entry: LearnedPatternEntry;
  readonly onSelect?: () => void;
}) {
  const scopeLabel = SCOPE_LABELS[entry.ownerScope] ?? entry.ownerScope;
  const reuseLabel = entry.reuseCount === 0 ? 'noch nie' : `${entry.reuseCount}×`;

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        disabled={!onSelect}
        className="w-full rounded border border-slate-700 bg-slate-900 p-3 text-left transition-colors hover:bg-slate-800 focus-visible:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-default disabled:bg-slate-900"
      >
        <div className="flex items-start gap-2">
          <LampDot verified={entry.verified} localExecutable={entry.localExecutable} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-slate-100 truncate">{entry.title}</span>
              <span className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-300 flex-shrink-0">
                {scopeLabel}
              </span>
              {entry.localExecutable && (
                <span className="rounded bg-green-900/50 border border-green-700/40 px-1.5 py-0.5 text-xs text-green-300 flex-shrink-0">
                  lokal
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-400 line-clamp-2">{entry.summary}</p>
            {entry.tags.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {entry.tags.slice(0, 5).map((tag) => (
                  <span key={tag} className="rounded bg-slate-800 px-1 py-0.5 text-xs text-slate-400">
                    {tag}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-1.5 flex gap-3 text-xs text-slate-500">
              <span>Wiederverwendet: {reuseLabel}</span>
            </div>
          </div>
        </div>
      </button>
    </li>
  );
}

export function PatternMemoryExplorer({
  entries,
  isBusy = false,
  onSelectEntry,
  onEraseUserData,
  eraseConfirmationText = '',
  onEraseConfirmationTextChange,
}: PatternMemoryExplorerProps) {
  const verifiedCount = entries.filter((e) => e.verified).length;
  const localExecutableCount = entries.filter((e) => e.localExecutable).length;
  const eraseReady = eraseConfirmationText.trim() === ERASE_CONFIRMATION && !isBusy && Boolean(onEraseUserData);

  return (
    <section className="w-full max-w-[393px] space-y-4 text-sm text-slate-200">
      <div>
        <h2 className="font-bold tracking-tight">Gelernte Patterns</h2>
        <p className="mt-0.5 text-xs text-slate-400">
          Sovereign lernt aus deiner Arbeit. Geprüfte Abläufe werden als lokale Patterns gespeichert.
        </p>
      </div>

      <div className="flex gap-4 rounded border border-slate-700 bg-slate-900 p-3">
        <div className="text-center">
          <div className="text-lg font-bold tabular-nums text-slate-100">{entries.length}</div>
          <div className="text-xs text-slate-400">gesamt</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold tabular-nums text-yellow-300">{verifiedCount}</div>
          <div className="text-xs text-slate-400">geprüft</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold tabular-nums text-green-400">{localExecutableCount}</div>
          <div className="text-xs text-slate-400">lokal</div>
        </div>
      </div>

      {entries.length === 0 && (
        <p className="text-xs text-slate-500 rounded border border-slate-800 bg-slate-900/60 p-3">
          Noch keine Patterns gespeichert. Nach erledigter Arbeit können Patterns vorgeschlagen werden.
        </p>
      )}

      {entries.length > 0 && (
        <ul className="space-y-2">
          {entries.map((entry) => (
            <PatternEntryRow
              key={entry.id}
              entry={entry}
              onSelect={onSelectEntry ? () => onSelectEntry(entry.id) : undefined}
            />
          ))}
        </ul>
      )}

      {onEraseUserData && onEraseConfirmationTextChange && (
        <div className="rounded border border-red-900/40 bg-slate-900/60 p-3 space-y-2">
          <p className="text-xs text-red-400 font-medium">Nutzerdaten löschen</p>
          <p className="text-xs text-slate-400">
            Entfernt alle lokalen und remote-Patterns. Geteilte abgeleitete Patterns bleiben erhalten,
            da sie keine personenbezogenen Daten enthalten.
          </p>
          <p className="text-xs text-slate-500">
            Zur Bestätigung: <span className="font-mono text-slate-300">{ERASE_CONFIRMATION}</span>
          </p>
          <input
            type="text"
            value={eraseConfirmationText}
            onChange={(e) => onEraseConfirmationTextChange(e.target.value)}
            disabled={isBusy}
            placeholder={ERASE_CONFIRMATION}
            className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-red-700 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={onEraseUserData}
            disabled={!eraseReady}
            className="rounded border border-red-800 bg-red-950/60 px-3 py-1 text-xs text-red-300 hover:bg-red-900/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Nutzerdaten löschen
          </button>
        </div>
      )}
    </section>
  );
}
