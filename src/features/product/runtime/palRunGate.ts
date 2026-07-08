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

  // Helper to check if intent is explicitly allowed for context
  const intentAllowed = (intent: PalRouterDecision['intent']): boolean => {
    switch (intent) {
      case 'answer':
        return context === 'chat' || context === 'repo-review';
      case 'repo-scan':
        return context === 'repo-review' || context === 'package-build';
      case 'code-change':
      case 'repair':
        return context === 'package-build';
      case 'draft-pr':
        return context === 'review-ready' || context === 'package-build';
      case 'unknown':
        // Unknown intents are only allowed in chat or package-build context
        return context === 'chat' || context === 'package-build';
      default:
        // Exhaustive check: should never reach here
        const _exhaustive: never = intent;
        return false;
    }
  };

  return intentAllowed(route.intent);
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
