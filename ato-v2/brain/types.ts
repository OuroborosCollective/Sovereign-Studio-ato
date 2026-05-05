export type ModelProvider = 'gemini-1.5-pro' | 'gemini-1.5-flash' | 'custom';

export type DecisionUrgency = 'low' | 'medium' | 'high' | 'critical';

export enum SignalImpact {
  MINIMAL = 'minimal',
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical'
}

export type SignalType = 'performance' | 'security' | 'user_intent' | 'system_health' | 'api_limit' | 'git_event';

export type ActionType = 'create' | 'update' | 'delete' | 'patch' | 'refactor' | 'optimize' | 'deploy' | 'rollback' | 'analyze';

export interface ArchitecturalAction {
  id: string;
  type: ActionType;
  path: string;
  description: string;
  payload?: string;
  dependencies?: string[];
  priority: number;
}

export interface ModelConfig {
  provider: ModelProvider;
  temperature: number;
  maxTokens: number;
  topP?: number;
  topK?: number;
}

export interface SystemSignal {
  id: string;
  type: SignalType;
  source: string;
  timestamp: number;
  impact: SignalImpact;
  payload: Record<string, unknown>;
  handled: boolean;
  metadata?: {
    platform?: 'android' | 'ios' | 'web';
    version?: string;
    targetId?: string;
  };
}

export interface BrainDecision {
  id: string;
  timestamp: number;
  type: 'architectural' | 'functional' | 'refactor' | 'optimization';
  action: string;
  rationale: string;
  confidence: number;
  impact: 'low' | 'medium' | 'high';
  changeset?: string[];
}

export interface DecisionContext {
  repositoryId: string;
  currentPath: string;
  fileContent?: string;
  gitDiff?: string;
  userIntent?: string;
  platform: 'android' | 'ios' | 'web';
  constraints: string[];
}

export interface EngineResult {
  decision: BrainDecision;
  rawResponse: string;
  latency: number;
  tokensUsed: {
    prompt: number;
    completion: number;
  };
}

export interface BrainCapability {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  requiredPermissions: string[];
}

export interface DecisionEngineInterface {
  analyze(context: DecisionContext): Promise<EngineResult>;
  refine(decisionId: string, feedback: string): Promise<BrainDecision>;
  execute(decision: BrainDecision): Promise<void>;
  processSignal(signal: SystemSignal): Promise<void>;
}

export type BrainStatus = 'idle' | 'processing' | 'learning' | 'error';

export interface BrainState {
  status: BrainStatus;
  lastDecision?: BrainDecision;
  config: ModelConfig;
  activeCapabilities: BrainCapability[];
  activeSignals: SystemSignal[];
}