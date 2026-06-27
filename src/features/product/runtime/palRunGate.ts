import {
  decidePalRoute,
  type PalAutomationMode,
  type PalRouterDecision,
} from './palRouter';

export type PalRunContext = 'chat' | 'repo-review' | 'package-build' | 'review-ready';
export type PalRunAction = 'answer' | 'load-repo' | 'inspect' | 'build' | 'review' | 'stop';

export interface PalRunGateInput {
  mission: string;
  repoReady: boolean;
  repoFileCount: number;
  context: PalRunContext;
  blockers?: string[];
  automationMode?: PalAutomationMode;
}

export interface PalRunGateDecision {
  allowed: boolean;
  action: PalRunAction;
  reason: string;
  route: PalRouterDecision;
}

function actionFor(context: PalRunContext, route: PalRouterDecision): PalRunAction {
  if (route.blocked) return route.signal === 'red' ? 'stop' : 'load-repo';
  if (context === 'chat' || route.intent === 'answer') return 'answer';
  if (context === 'repo-review' || route.intent === 'repo-scan') return 'inspect';
  if (context === 'review-ready' || route.intent === 'draft-pr') return 'review';
  return 'build';
}

function contextAllows(context: PalRunContext, route: PalRouterDecision): boolean {
  if (route.blocked) return false;
  if (context === 'chat') return route.intent === 'answer' || route.intent === 'unknown';
  if (context === 'repo-review') return route.intent === 'repo-scan' || route.intent === 'answer' || route.intent === 'unknown';
  if (context === 'review-ready') return route.intent === 'draft-pr';
  return route.intent === 'code-change' || route.intent === 'repair' || route.intent === 'draft-pr' || route.intent === 'unknown';
}

export function decidePalRunGate(input: PalRunGateInput): PalRunGateDecision {
  const route = decidePalRoute({
    mission: input.mission,
    repoReady: input.repoReady,
    repoFileCount: input.repoFileCount,
    blockers: input.blockers,
    automationMode: input.automationMode,
  });
  const action = actionFor(input.context, route);
  const allowed = contextAllows(input.context, route);

  return {
    allowed,
    action,
    reason: allowed ? route.reason : route.blocked ? route.reason : `PAL route ${route.intent} is not allowed for ${input.context}.`,
    route,
  };
}

export function assertPalRunGateAllowed(input: PalRunGateInput): PalRunGateDecision {
  const decision = decidePalRunGate(input);
  if (!decision.allowed) throw new Error(`PAL_RUN_GATE_STOPPED: ${decision.reason}`);
  return decision;
}
