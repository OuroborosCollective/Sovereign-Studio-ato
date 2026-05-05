export type ModelProvider = 'gemini-1.5-pro' | 'gemini-1.5-flash' | 'custom';

export type DecisionUrgency = 'low' | 'medium' | 'high' | 'critical';

export interface ModelConfig {
  provider: ModelProvider;
  temperature: number;
  maxTokens: number;
  topP?: number;
  topK?: number;
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
}

export type BrainStatus = 'idle' | 'processing' | 'learning' | 'error';

export interface BrainState {
  status: BrainStatus;
  lastDecision?: BrainDecision;
  config: ModelConfig;
  activeCapabilities: BrainCapability[];
}