import React from 'react';

export type OperatorLamp = 'green' | 'yellow' | 'red';

export interface OperatorCoachPanelProps {
  lamp: OperatorLamp;
  headline: string;
  message: string;
  nextAction: string;
  isThinking: boolean;
  onRepo: () => void;
  onBuilder: () => void;
  onFiles: () => void;
  onLogs: () => void;
}

const lampClass: Record<OperatorLamp, string> = {
  green: 'bg-emerald-400 shadow-emerald-400/50',
  yellow: 'bg-amber-300 shadow-amber-300/50',
  red: 'bg-rose-400 shadow-rose-400/50',
};

const frameClass: Record<OperatorLamp, string> = {
  green: 'border-emerald-400/35 bg-emerald-500/10',
  yellow: 'border-amber-400/35 bg-amber-500/10',
  red: 'border-rose-400/35 bg-rose-500/10',
};

const lampLabels: Record<OperatorLamp, string> = {
  green: 'Status: Grün (Betriebsbereit)',
  yellow: 'Status: Gelb (Hinweis)',
  red: 'Status: Rot (Blockiert)',
};

const actionButtonClass =
  'rounded-lg border border-slate-700/50 bg-slate-900/60 px-3 py-2 font-medium text-slate-200 transition-colors hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400';

export function OperatorCoachPanel({
  lamp,
  headline,
  message,
  nextAction,
  isThinking,
  onRepo,
  onBuilder,
  onFiles,
  onLogs,
}: OperatorCoachPanelProps) {
  return (
    <section
      className={`mt-4 rounded-3xl border p-4 text-sm text-slate-100 ${frameClass[lamp]}`}
      data-testid="operator-coach-panel"
      aria-labelledby="operator-coach-heading"
    >
      <div className="flex flex-wrap items-start gap-3">
        <div
          className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-300/30 bg-slate-950/70 text-2xl shadow-lg shadow-cyan-950/30"
          aria-hidden="true"
        >
          🤖
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`h-3 w-3 rounded-full shadow-lg ${lampClass[lamp]}`}
              aria-label={lampLabels[lamp]}
              title={lampLabels[lamp]}
            />
            <h2 id="operator-coach-heading" className="font-black tracking-tight text-white">
              Sovereign Bot · {headline}
            </h2>
            {isThinking ? (
              <span className="thinking-dots text-cyan-200" aria-label="arbeitet">
                ...
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-200">{message}</p>
          <p className="mt-1 text-xs font-bold leading-5 text-white">Naechster Schritt: {nextAction}</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <button
          type="button"
          onClick={onRepo}
          className={actionButtonClass}
          aria-label="Zum Repository-Bereich wechseln"
          title="Zum Repository-Bereich wechseln"
        >
          Repo
        </button>
        <button
          type="button"
          onClick={onBuilder}
          className={actionButtonClass}
          aria-label="Zum Mission-Builder wechseln"
          title="Zum Mission-Builder wechseln"
        >
          Builder
        </button>
        <button
          type="button"
          onClick={onFiles}
          className={actionButtonClass}
          aria-label="Zu Dateien und Diff-Vorschau wechseln"
          title="Zu Dateien und Diff-Vorschau wechseln"
        >
          Files / Diff
        </button>
        <button
          type="button"
          onClick={onLogs}
          className={actionButtonClass}
          aria-label="Zum Runtime-Monitor wechseln"
          title="Zum Runtime-Monitor wechseln"
        >
          Monitor
        </button>
      </div>
    </section>
  );
}
