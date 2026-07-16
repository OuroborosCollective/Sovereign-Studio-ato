import type { SovereignActionEventInput } from '../features/product/runtime/sovereignActionStreamRuntime';
import type {
  SovereignExecutorDecision,
  SovereignExecutorRouteInput,
} from '../features/product/runtime/sovereignExecutorRuntime';
import { decideSovereignExecutorRoute } from '../features/product/runtime/sovereignExecutorRuntime';
import { decideSovereignInternalOperator } from './sovereignInternalOperatorRuntime';

export type SovereignExecutorBridgeRoute =
  | 'executor_runtime'
  | 'sovereign_internal_operator';

export interface SovereignExecutorBridgeDecision {
  readonly bridgeRoute: SovereignExecutorBridgeRoute;
  readonly state: 'allowed' | 'blocked';
  readonly reason: string;
  readonly nextAction: string;
  readonly event: SovereignActionEventInput;
  readonly executorRoute?: SovereignExecutorDecision['route'];
  readonly executorActionRoute?: SovereignExecutorDecision['actionRoute'];
  readonly internalOperatorRoute?: string;
  readonly internalOperatorConfidence?: number;
  readonly internalOperatorStages?: readonly string[];
}

function internalOperatorEvent(reason: string, state: 'queued' | 'blocked'): SovereignActionEventInput {
  return {
    route: 'toolchain',
    kind: state === 'queued' ? 'route_selected' : 'blocked',
    label: state === 'queued' ? 'Interner Sovereign Operator eingeplant' : 'Interner Sovereign Operator blockiert',
    detail: reason,
    state,
  };
}

function shouldTryInternalOperator(input: SovereignExecutorRouteInput): boolean {
  if (input.intent !== 'code_execution') return false;
  if (!input.capabilities.repo.canStart) return false;
  if (!input.capabilities.githubWrite.canStart) return false;
  return true;
}

export function decideSovereignExecutorBridgeRoute(
  input: SovereignExecutorRouteInput,
): SovereignExecutorBridgeDecision {
  const executorDecision = decideSovereignExecutorRoute(input);

  if (executorDecision.state === 'allowed') {
    return {
      bridgeRoute: 'executor_runtime',
      state: 'allowed',
      reason: executorDecision.reason,
      nextAction: executorDecision.nextAllowedAction,
      event: executorDecision.event,
      executorRoute: executorDecision.route,
      executorActionRoute: executorDecision.actionRoute,
    };
  }

  if (!shouldTryInternalOperator(input)) {
    return {
      bridgeRoute: 'executor_runtime',
      state: 'blocked',
      reason: executorDecision.reason,
      nextAction: executorDecision.nextAllowedAction,
      event: executorDecision.event,
      executorRoute: executorDecision.route,
      executorActionRoute: executorDecision.actionRoute,
    };
  }

  const operatorDecision = decideSovereignInternalOperator({
    intent: input.intent,
    taskComplexity: input.taskComplexity,
    capabilities: input.capabilities,
    candidatePath: input.candidatePath,
  });

  if (operatorDecision.state === 'blocked') {
    return {
      bridgeRoute: 'sovereign_internal_operator',
      state: 'blocked',
      reason: operatorDecision.reason,
      nextAction: operatorDecision.nextAction,
      event: internalOperatorEvent(operatorDecision.reason, 'blocked'),
      internalOperatorRoute: operatorDecision.route,
      internalOperatorConfidence: operatorDecision.confidence,
      internalOperatorStages: operatorDecision.stages,
    };
  }

  return {
    bridgeRoute: 'sovereign_internal_operator',
    state: 'allowed',
    reason: operatorDecision.reason,
    nextAction: operatorDecision.nextAction,
    event: internalOperatorEvent(operatorDecision.reason, 'queued'),
    internalOperatorRoute: operatorDecision.route,
    internalOperatorConfidence: operatorDecision.confidence,
    internalOperatorStages: operatorDecision.stages,
  };
}
