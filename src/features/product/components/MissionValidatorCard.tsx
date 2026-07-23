import type { MissionValidationResult } from '../runtime/missionValidatorRuntime';

interface MissionValidatorCardProps {
  readonly result: MissionValidationResult;
  readonly onContinue: () => void;
  readonly onEdit: () => void;
}

export function MissionValidatorCard({ result, onContinue, onEdit }: MissionValidatorCardProps) {
  return (
    <section className="mx-3 my-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm" data-testid="mission-validator-card">
      <div className="flex items-center justify-between gap-3">
        <strong>Pre-flight Mission Validator</strong>
        <span className="rounded-full border border-amber-400/50 px-2 py-1 font-mono text-xs">{result.score}/100</span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Die Mission ist noch breit. Das ist eine Warnung, kein erfundener Runtime-Blocker.
      </p>
      {result.questions.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
          {result.questions.map((question) => <li key={question}>{question}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="rounded-md border px-3 py-2 text-xs" onClick={onEdit}>Mission ergänzen</button>
        <button type="button" className="rounded-md bg-amber-500 px-3 py-2 text-xs font-semibold text-black" onClick={onContinue}>Trotzdem starten</button>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Quelle: {result.status === 'ready' ? `${result.resolvedTransport || 'Modellroute'}${result.modelUsed ? ` · ${result.modelUsed}` : ''}` : 'deterministischer Fallback'}
      </p>
    </section>
  );
}
