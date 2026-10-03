import type { SovereignAgentRuntimeEvidence } from '../../product/runtime/sovereignAgentRuntime';

export type AgentMode = 'single' | 'swarm';
export type ExecutionMode = 'free' | 'paid';

export type JobPhase =
  | 'IDLE'
  | 'AWAKENING'
  | 'DISPATCHING'
  | 'PROVISIONING'
  | 'EXECUTING'
  | 'AWAITING_OWNER_INPUT'
  | 'FINALIZING'
  | 'BLOCKED'
  | 'READY_TO_PUBLISH'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface WorkspaceState {
  modifiedFiles: string[];
  /** Exact repository revision when bound by job/evidence readback. */
  currentRevision: string;
  /** Distinguishes live, stale and unavailable readback without fabricating progress. */
  readbackState?: 'live' | 'stale' | 'unavailable';
  readbackError?: string;
  liveProjectionKinds?: string[];
  diffStats?: { additions: number; deletions: number; filesChanged: number };
  fileDetails?: Array<{ path: string; status: 'modified' | 'added' | 'deleted'; diff: string }>;
}

export interface OwnerInteraction {
  id: string;
  prompt: string;
  options?: string[];
  requiresText: boolean;
  timestamp?: string;
  context?: string;
  /** Server-owned approval/directive category; presentation-only, never an authority grant. */
  kind?: string;
}

export interface OwnerInteractionResponse { interactionId: string; response: string; }

/** A Draft PR exists here only after the backend returned complete GitHub readback evidence. */
export interface DraftPR {
  url: string;
  revision: string;
  signature?: string;
  pullRequestNumber: number;
  title?: string;
  branch: string;
  baseBranch: string;
  verifiedRevisionHash: string;
  publishedHeadSha: string;
  readbackHeadSha: string;
  ciState: 'none' | 'pending' | 'success' | 'failure';
  draftVerified: true;
  readbackVerified: true;
  checksReadbackVerified: true;
  checkRunCount: number;
  checksPendingCount: number;
  checksSuccessCount: number;
  checksFailureCount: number;
  statusContextCount: number;
  timestamp?: string;
}

export interface PublicationState {
  draftPR?: DraftPR;
  verificationLedgerHash?: string;
  signatureVerified?: boolean;
}

export interface DraftPrPreparation {
  allowed: boolean;
  decision: string;
  summary?: string;
  headBranch?: string;
  baseBranch?: string;
  nextAction?: string;
  blockers: string[];
}

export interface SovereignJob {
  /** vNext mission handle = persisted Agents SDK runId. */
  id: string;
  runId: string;
  backendJobId?: string;
  phase: JobPhase;
  createdAt: string;
  updatedAt: string;
  logs: string[];
  workspaceState: WorkspaceState;
  workspace?: WorkspaceState;
  pendingInteraction?: OwnerInteraction;
  draftPR?: DraftPR;
  publication?: PublicationState;
  draftPrPreparation?: DraftPrPreparation;
  sourceStatus?: string;
  nextAction?: string;
  assistantMessage?: string;
  error?: { message: string; code?: string };
  serverObservedAt?: string;
  readbackReceivedMonotonicMs?: number;
  lastEventAt?: string;
  lastHeartbeatAt?: string;
  persistedEventCount?: number;
  externalRef?: string;
  runtimeEvidence?: SovereignAgentRuntimeEvidence;
}

export interface Toolchain {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'inactive';
  driver?: string;
  latencyMs?: number;
  badge?: string;
}
export type ToolchainAttachment = Toolchain;

export interface Skill {
  id: string;
  name: string;
  source: 'core' | 'learned';
  description: string;
  efficiency?: number;
  runsApplied?: number;
  tier?: 'Alpha' | 'Beta' | 'Neural' | 'Sovereign';
}
export type SkillNode = Skill;

export interface IntegrationAttachment {
  id: string;
  type?: 'webhook' | 'artifact_store' | 'audit_ledger' | 'event_stream';
  name: string;
  status: 'connected' | 'disconnected' | 'verified' | 'blocked' | 'degraded' | 'isolated' | 'defined_not_run';
  source?: string;
  observedAt?: string;
  boundary?: string;
  blocker?: string;
  readbackSha256?: string;
  enabled?: boolean;
  endpoint?: string;
  eventsProcessed?: number;
}
export type IntegrationArchitectureAttachment = IntegrationAttachment;

export interface RuntimeAgentNode {
  id: string;
  name: string;
  kind: 'executor' | 'agent';
  status: string;
  persistedStatus?: string;
  source: string;
  description: string;
  jobId?: string;
  runId?: string;
  taskId?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface ControlSurfaceReadback {
  schemaVersion: 'sovereign.control-surface-readback.v1';
  jobId: string | null;
  jobExecutionMode?: ExecutionMode;
  observedAt: string;
  receivedMonotonicMs: number;
  agents: RuntimeAgentNode[];
  agentReadbackState: 'live' | 'unavailable';
  agentBlocker?: string;
  integrations: IntegrationAttachment[];
  integrationReadbackState: 'live' | 'unavailable';
  integrationBlocker?: string;
  credits: {
    readbackState: 'live' | 'unavailable';
    creditStateVerified: boolean;
    credits?: number;
    providerFundedCredits?: number;
    paidEntitlementVerified?: boolean;
    paidEntitlementSource?: string;
    blocker?: string;
  };
  routing: { repositoryMode: 'free'; agentMode: 'single'; modes: Array<{
    mode: 'free' | 'paid'; available: boolean; providerAvailable: boolean;
    model?: string; routeId?: string; profileId?: string; blocker?: string; executionBlocker?: string;
  }> };
}

export interface ChatMessage {
  id: string;
  role?: 'human' | 'system' | 'agent' | 'assistant';
  sender?: 'HUMAN' | 'SOVEREIGN_SWARM' | 'SOVEREIGN_AGENT' | 'SYSTEM' | 'RUNTIME_MONITOR';
  content: string;
  timestamp: string;
  evidenceBadge?: string;
  metadata?: { jobId?: string; phase?: JobPhase; executionTimeMs?: number };
}
