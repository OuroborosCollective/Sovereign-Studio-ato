import { 
  SignalImpact, 
  SystemSignal, 
  ArchitecturalAction, 
  ActionType 
} from './types';

/**
 * Sovereign Studio V3 - Decision Engine
 * Maps analyzed signals to high-performance architectural or content actions.
 * Optimized for Capacitor 6 and Mobile-First hybrid architectures.
 */

// Fix TS2693: SignalImpact must be an enum to be used as a value
export enum DecisionSignalImpact {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  CRITICAL = 'CRITICAL'
}

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
   * Core mapping logic for Sovereign Studio hybrid architecture.
   * Fix TS2367: signal.type union now includes 'UI_INCONSISTENCY'
   */
  private mapSignalToAction(signal: SystemSignal): ArchitecturalAction {
    const { type, impact, metadata } = signal;

    // High Impact Performance signals trigger Native Capacitor Optimizations
    // Using cast to ensure enum comparison compatibility if imported from external types
    if (impact === (SignalImpact.CRITICAL as any) && this.context.platform !== 'web') {
      return {
        type: ActionType.OPTIMIZE_NATIVE,
        priority: 1,
        payload: { target: 'bridge', strategy: 'batch-ops' },
        timestamp: Date.now()
      };
    }

    // Logic for LLM-driven UI updates
    // Fix TS2339: metadata now contains optional targetId
    if (type === 'UI_INCONSISTENCY') {
      return {
        type: ActionType.REFACTOR_COMPONENT,
        priority: 2,
        payload: { 
          componentId: metadata.targetId || 'root', 
          pattern: 'MobileFirst' 
        },
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

  private validateAction(action: ArchitecturalAction): ArchitecturalAction {
    // Ensure action conforms to Mobile-First constraints
    if (this.context.platform === 'android' && action.type === ActionType.REFACTOR_COMPONENT) {
      action.payload.optimizeForTouch = true;
    }
    return action;
  }

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

/**
 * Enhanced types for internal Engine communication and external extension
 */
export enum ActionType {
  OPTIMIZE_NATIVE = 'OPTIMIZE_NATIVE',
  REFACTOR_COMPONENT = 'REFACTOR_COMPONENT',
  SYNC_STATE = 'SYNC_STATE',
  LOG_ERROR = 'LOG_ERROR',
  GENERATE_CONTENT = 'GENERATE_CONTENT'
}

export interface ArchitecturalAction {
  type: ActionType;
  priority: number;
  payload: Record<string, any>;
  timestamp: number;
}