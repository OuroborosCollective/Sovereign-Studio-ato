import type { MissionValidationResult } from '../runtime/missionValidatorRuntime';

interface MissionValidatorCardProps {
  readonly result: MissionValidationResult;
  readonly onContinue: () => void;
  readonly onEdit: () => void;
}

export function MissionValidatorCard({ result, onContinue, onEdit }: MissionValidatorCardProps) {
  const scoreTooltip = `Bewertung: ${result.score} von 100`;

  return (
    <section
      className="mx-3 my-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm"
      data-testid="mission-validator-card"
      aria-label="Pre-flight Mission Validator"
      aria-labelledby="mission-validator-title"
    >
      <div className="flex items-center justify-between gap-3">
        <strong id="mission-validator-title">Pre-flight Mission Validator</strong>
        <span
          className="rounded-full border border-amber-400/50 px-2 py-1 font-mono text-xs"
          title={scoreTooltip}
          aria-label={scoreTooltip}
        >
          {result.score}/100
        </span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Die Mission ist noch breit. Das ist eine Warnung, kein erfundener Runtime-Blocker.
      </p>
      {result.questions.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs" role="list">
          {result.questions.map((question) => <li key={question}>{question}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md border border-amber-500/30 px-3 py-2 text-xs hover:bg-amber-500/20 focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:outline-none"
          onClick={onEdit}
          title="Mission mit weiteren Details ergänzen"
          aria-label="Mission ergänzen"
        >
          Mission ergänzen
        </button>
        <button
          type="button"
          className="rounded-md bg-amber-500 px-3 py-2 text-xs font-semibold text-black hover:bg-amber-400 focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:outline-none"
          onClick={onContinue}
          title="Auftrag trotz Warnung unverändert starten"
          aria-label="Trotzdem starten"
        >
          Trotzdem starten
        </button>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Quelle: {result.status === 'ready' ? `${result.resolvedTransport || 'Modellroute'}${result.modelUsed ? ` · ${result.modelUsed}` : ''}` : 'deterministischer Fallback'}
      </p>
    </section>
  );
}
