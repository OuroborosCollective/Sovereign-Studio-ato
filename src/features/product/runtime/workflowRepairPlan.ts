import type { WorkflowWatchReport, WorkflowCheckItem } from './workflowWatch';

export type WorkflowRepairSeverity = 'none' | 'low' | 'medium' | 'high';

export interface WorkflowRepairAction {
  id: string;
  title: string;
  rationale: string;
  suggestedFiles: string[];
}

export interface WorkflowRepairPlan {
  severity: WorkflowRepairSeverity;
  mission: string;
  actions: WorkflowRepairAction[];
  blocked: boolean;
  reason: string;
  summary: string;
}

function slug(input: string): string {
  return input.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48) || 'workflow-check';
}

function checkText(check: WorkflowCheckItem): string {
  return `${check.name} ${check.summary} ${check.conclusion ?? ''}`.toLowerCase();
}

function suggestedFilesForCheck(check: WorkflowCheckItem): string[] {
  const text = checkText(check);
  const files = new Set<string>();

  if (text.includes('lint') || text.includes('eslint')) {
    files.add('src/**/*');
    files.add('eslint.config.*');
    files.add('package.json');
  }
  if (text.includes('test') || text.includes('vitest') || text.includes('jest')) {
    files.add('src/**/*.test.ts');
    files.add('src/**/*.test.tsx');
    files.add('package.json');
  }
  if (text.includes('build') || text.includes('vite') || text.includes('tsc') || text.includes('type')) {
    files.add('tsconfig.json');
    files.add('vite.config.*');
    files.add('src/**/*');
  }
  if (text.includes('workflow') || text.includes('action') || text.includes('ci')) {
    files.add('.github/workflows/*');
  }
  if (text.includes('lockfile') || text.includes('pnpm') || text.includes('npm') || text.includes('install')) {
    files.add('package.json');
    files.add('pnpm-lock.yaml');
    files.add('package-lock.json');
  }

  if (!files.size) {
    files.add('README.md');
    files.add('docs/LAUNCH_READINESS.md');
  }

  return Array.from(files);
}

function actionForCheck(check: WorkflowCheckItem): WorkflowRepairAction {
  const id = `repair-${slug(check.name)}`;
  return {
    id,
    title: `Repair ${check.name}`,
    rationale: check.summary || `Workflow check ${check.name} ended with ${check.status}.`,
    suggestedFiles: suggestedFilesForCheck(check),
  };
}

export function buildWorkflowRepairPlan(report: WorkflowWatchReport | null): WorkflowRepairPlan {
  if (!report) {
    return {
      severity: 'none',
      mission: 'No workflow report is available yet.',
      actions: [],
      blocked: true,
      reason: 'Create a Draft PR and run Workflow Watch before preparing a repair plan.',
      summary: 'No workflow report available.',
    };
  }

  const failedChecks = report.checks.filter((check) => check.status === 'red');
  const pendingChecks = report.checks.filter((check) => check.status === 'pending');

  if (report.status === 'green') {
    return {
      severity: 'none',
      mission: 'No repair needed. Workflow checks are green.',
      actions: [],
      blocked: true,
      reason: 'Workflow checks are green.',
      summary: 'No repair needed.',
    };
  }

  if (pendingChecks.length && !failedChecks.length) {
    return {
      severity: 'low',
      mission: 'Wait for pending workflow checks before creating a repair package.',
      actions: pendingChecks.map(actionForCheck),
      blocked: true,
      reason: 'Checks are still pending. Creating a repair package now may target the wrong issue.',
      summary: `${pendingChecks.length} pending check(s). Wait before repair.`,
    };
  }

  if (!failedChecks.length && report.errors.length) {
    return {
      severity: 'medium',
      mission: 'Repair GitHub workflow watch access or token visibility before generating code changes.',
      actions: [{
        id: 'repair-workflow-access',
        title: 'Repair workflow access',
        rationale: report.errors.join(' '),
        suggestedFiles: ['docs/SOVEREIGN_RUNTIME.md', 'docs/LAUNCH_READINESS.md'],
      }],
      blocked: false,
      reason: 'Workflow Watch reported access or repository errors.',
      summary: `${report.errors.length} workflow watch error(s).`,
    };
  }

  if (!failedChecks.length) {
    return {
      severity: 'low',
      mission: 'No failed workflow checks were found. Re-run Workflow Watch after checks finish.',
      actions: [],
      blocked: true,
      reason: 'No failed checks available to target.',
      summary: 'No failed workflow checks found.',
    };
  }

  const actions = failedChecks.map(actionForCheck);
  const affectedFiles = Array.from(new Set(actions.flatMap((action) => action.suggestedFiles)));
  const mission = [
    'Workflow repair package:',
    `Fix ${failedChecks.length} failed GitHub workflow check(s).`,
    `Target checks: ${failedChecks.map((check) => check.name).join(', ')}.`,
    `Inspect likely files: ${affectedFiles.join(', ')}.`,
    'Keep changes minimal, guarded, and test-backed.',
  ].join(' ');

  return {
    severity: failedChecks.length > 1 ? 'high' : 'medium',
    mission,
    actions,
    blocked: false,
    reason: 'Failed workflow checks are available for targeted repair.',
    summary: `${failedChecks.length} failed check(s), ${actions.length} repair action(s).`,
  };
}

export function assertWorkflowRepairPlanReady(plan: WorkflowRepairPlan): void {
  if (plan.blocked) throw new Error(plan.reason);
  if (!plan.actions.length) throw new Error('Workflow repair plan has no actions.');
}
