import type {
  DraftPR,
  DraftPrPreparation,
  IntegrationAttachment,
  Skill,
  SovereignJob,
  Toolchain,
} from '../types/domain';

export interface AdapterStatus {
  mode: 'live_http';
  backendUrl: string;
  isFallback: false;
  lastPingMs?: number;
  errorMessage?: string;
}

export interface RestoredRepositoryRun {
  jobId: string;
  mission?: string;
  status?: string;
  repoUrl?: string;
  branch?: string;
}

export interface SovereignBackendAdapter {
  runRepositoryExecution(mission: string): Promise<{ jobId: string }>;
  getJob(runId: string): Promise<SovereignJob>;
  resumeJob(runId: string, interactionId: string, response: string): Promise<void>;
  abortJob(runId: string): Promise<void>;
  prepareDraftPr(runId: string): Promise<DraftPrPreparation>;
  createDraftPr(runId: string): Promise<DraftPR>;
  getToolchains(): Promise<Toolchain[]>;
  getSkills(): Promise<Skill[]>;
  getIntegrations(): Promise<IntegrationAttachment[]>;
  restoreLatestRepositoryRun?(): Promise<RestoredRepositoryRun | null>;
  getStatus?(): AdapterStatus;
  checkHealth?(): Promise<{ status: string; latencyMs: number }>;
}
