import type { WorkflowRepairPlan } from '../runtime/workflowRepairPlan';

export interface WorkflowRepairPanelProps {
  plan: WorkflowRepairPlan;
  onUseMission: (mission: string) => void;
}

function severityClass(severity: string): string {
  if (severity === 'high') return 'text-red-300';
  if (severity === 'medium') return 'text-amber-300';
  if (severity === 'low') return 'text-sky-300';
  return 'text-emerald-300';
}

export function WorkflowRepairPanel({ plan, onUseMission }: WorkflowRepairPanelProps) {
  const buttonTitle = plan.blocked
    ? 'Repair mission blocked'
    : 'Use repair mission in builder';

  const buttonAriaLabel = plan.blocked
    ? 'Repair mission blocked'
    : 'Use repair mission in builder';

  return (
    <section
      className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
      aria-labelledby="workflow-repair-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="workflow-repair-heading" className="font-bold">Workflow Repair Planner</h2>
          <p className="mt-1 text-xs text-slate-400">{plan.summary}</p>
        </div>
        <span
          className={`rounded bg-slate-900 px-2 py-1 text-xs font-bold uppercase ${severityClass(plan.severity)}`}
          title={`Severity: ${plan.severity}`}
          aria-label={`Severity: ${plan.severity}`}
        >
          {plan.severity}
        </span>
      </div>

      <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
        <p className="text-xs text-slate-400">{plan.reason}</p>
        <pre
          tabIndex={0}
          aria-label="Repair Mission Content"
          className="mt-3 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-3 text-xs text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
        >
          {plan.mission}
        </pre>
        <button
          className="mt-3 rounded bg-sky-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:pointer-events-none disabled:opacity-50"
          disabled={plan.blocked}
          onClick={() => onUseMission(plan.mission)}
          type="button"
          title={buttonTitle}
          aria-label={buttonAriaLabel}
        >
          Use Repair Mission in Builder
        </button>
      </div>

      {plan.actions.length ? (
        <ul role="list" aria-label="Suggested repair actions" className="mt-4 grid gap-3">
          {plan.actions.map((action) => (
            <li key={action.id} className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <h3 className="font-bold text-slate-100">{action.title}</h3>
              <p className="mt-1 text-xs text-slate-400">{action.rationale}</p>
              <p className="mt-2 text-[11px] text-slate-500">Likely files: {action.suggestedFiles.join(', ')}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
