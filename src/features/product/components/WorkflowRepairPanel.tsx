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
  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Workflow Repair Planner</h2>
          <p className="mt-1 text-xs text-slate-400">{plan.summary}</p>
        </div>
        <span className={`rounded bg-slate-900 px-2 py-1 text-xs font-bold uppercase ${severityClass(plan.severity)}`}>
          {plan.severity}
        </span>
      </div>

      <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
        <p className="text-xs text-slate-400">{plan.reason}</p>
        <pre className="mt-3 whitespace-pre-wrap rounded bg-black/40 p-3 text-xs text-slate-300">{plan.mission}</pre>
        <button
          className="mt-3"
          disabled={plan.blocked}
          onClick={() => onUseMission(plan.mission)}
          type="button"
        >
          Use Repair Mission in Builder
        </button>
      </div>

      {plan.actions.length ? (
        <div className="mt-4 grid gap-3">
          {plan.actions.map((action) => (
            <div key={action.id} className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <h3 className="font-bold text-slate-100">{action.title}</h3>
              <p className="mt-1 text-xs text-slate-400">{action.rationale}</p>
              <p className="mt-2 text-[11px] text-slate-500">Likely files: {action.suggestedFiles.join(', ')}</p>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
