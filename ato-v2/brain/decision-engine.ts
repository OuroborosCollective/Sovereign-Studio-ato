import { 
  SignalImpact, 
  SystemSignal,
  ActionType,
  ArchitecturalAction
} from './types';

/**
 * Sovereign Studio V3 - Decision Engine
 * Maps analyzed signals to high-performance architectural or content actions.
 * Optimized for Gemini API integration and Capacitor 6 hybrid workflows.
 */

export enum DecisionState {
  IDLE = 'IDLE',
  EVALUATING = 'EVALUATING',
  MAPPING = 'MAPPING',
  EXECUTING = 'EXECUTING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED'
}

export interface DecisionContext {
  platform: 'web' | 'ios' | 'android';
  performanceMetrics: Record<string, number>;
  activeModule: string;
}

export class DecisionEngine {
  private currentState: DecisionState = DecisionState.IDLE;
  private lastAction: ArchitecturalAction | null = null;

  constructor(private readonly context: DecisionContext) {}

  /**
   * Processes an incoming signal and produces a strategic architectural action.
   */
  public async decide(signal: SystemSignal): Promise<ArchitecturalAction> {
    this.currentState = DecisionState.EVALUATING;

    try {
      const action = this.mapSignalToAction(signal);
      this.currentState = DecisionState.MAPPING;
      
      this.lastAction = this.validateAction(action);
      this.currentState = DecisionState.COMPLETED;
      
      return this.lastAction;
    } catch (error) {
      this.currentState = DecisionState.FAILED;
      return this.fallbackAction(signal);
    }
  }

  /**
   * Core mapping logic for Sovereign Studio V3 hybrid architecture.
   * Fixes TS2367 by explicitly handling the SignalType union including 'UI_INCONSISTENCY'.
   */
  private mapSignalToAction(signal: SystemSignal): ArchitecturalAction {
    const { type, impact, metadata } = signal;

    // High Impact Performance signals trigger Native Capacitor Optimizations
    // Fix TS2693: Explicitly using SignalImpact enum values for comparison
    if (impact === SignalImpact.CRITICAL && this.context.platform !== 'web') {
      return {
        type: ActionType.OPTIMIZE_NATIVE,
        priority: 1,
        payload: { target: 'bridge', strategy: 'batch-ops' },
        timestamp: Date.now()
      };
    }

    // Logic for LLM-driven UI updates (Fixes TS2367)
    if (type === 'UI_INCONSISTENCY') {
      return {
        type: ActionType.REFACTOR_COMPONENT,
        priority: 2,
        payload: { componentId: metadata.targetId, pattern: 'MobileFirst' },
        timestamp: Date.now()
      };
    }

    // Default to content synchronization
    return {
      type: ActionType.SYNC_STATE,
      priority: 3,
      payload: { scope: 'global' },
      timestamp: Date.now()
    };
  }

  /**
   * Ensures action conforms to Mobile-First constraints and platform-specific requirements.
   */
  private validateAction(action: ArchitecturalAction): ArchitecturalAction {
    if (this.context.platform === 'android' && action.type === ActionType.REFACTOR_COMPONENT) {
      action.payload.optimizeForTouch = true;
    }
    return action;
  }

  /**
   * Provides a safe fallback in case of mapping failures.
   */
  private fallbackAction(signal: SystemSignal): ArchitecturalAction {
    return {
      type: ActionType.LOG_ERROR,
      priority: 0,
      payload: { originalSignal: signal.type, error: 'Transition mapping failed' },
      timestamp: Date.now()
    };
  }

  public getState(): DecisionState {
    return this.currentState;
  }
}