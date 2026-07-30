export type RescueFailureFamily =
  | 'github_actions_ci'
  | 'docker_compose_container'
  | 'postgresql_migration_schema';

export interface RescueDiagnosis {
  readonly schemaVersion: string;
  readonly ok: boolean;
  readonly supported: boolean;
  readonly mutationPerformed: false;
  readonly repository: string;
  readonly baseBranch: string;
  readonly baseSha: string;
  readonly failureFamily: RescueFailureFamily;
  readonly failureFamilyTitle: string;
  readonly riskClass: string;
  readonly affectedFiles: string[];
  readonly repairProposal: string;
  readonly verificationPlan: string[];
  readonly evidenceSha256: string;
  readonly outcomeContract: {
    readonly contractSha256: string;
    readonly repairPack: {
      readonly id: string;
      readonly credits: number;
      readonly maxChangedFiles: number;
      readonly maxRepairAttempts: number;
      readonly draftPrOnly: true;
      readonly autoMerge: false;
    };
    readonly successConditions: string[];
    readonly stopConditions: string[];
  };
}

export interface RescueEntitlement {
  readonly entitled: boolean;
  readonly source: string;
  readonly purchaseVerified: boolean;
  readonly privileged: boolean;
  readonly availableCredits: number;
  readonly requiredCredits: number;
  readonly repairPackId: string;
  readonly serverSideVerified: true;
  readonly checkout: { readonly required: boolean; readonly surface: 'existing-paywall-modal'; readonly external: true };
}

export interface RescueRepair {
  readonly repairId: string;
  readonly jobId: string;
  readonly runId?: string;
  readonly state: string;
  readonly chargedCredits: number;
  readonly duplicate?: boolean;
}

export interface RescueProofPack {
  readonly ready: boolean;
  readonly proofSha256: string;
  readonly baseSha: string;
  readonly headSha?: string;
  readonly publishedHeadSha?: string;
  readonly draftPr: boolean;
  readonly draftPrUrl?: string;
  readonly changedFiles: string[];
  readonly blockers: string[];
}

interface RequestInput {
  readonly repository: string;
  readonly baseBranch: string;
  readonly evidenceText: string;
  readonly failureFamily?: RescueFailureFamily;
}

function endpoint(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}

async function responseObject(response: Response): Promise<Record<string, unknown>> {
  const text = await response.text();
  const body = text.trim() ? JSON.parse(text) as unknown : {};
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error('Sovereign Rescue returned an invalid response.');
  }
  const value = body as Record<string, unknown>;
  if (!response.ok) {
    const message = typeof value.error === 'string'
      ? value.error
      : typeof value.blocker === 'string'
        ? value.blocker
        : `Sovereign Rescue returned HTTP ${response.status}.`;
    const error = new Error(message) as Error & { status?: number; payload?: Record<string, unknown> };
    error.status = response.status;
    error.payload = value;
    throw error;
  }
  return value;
}

function headers(idempotencyKey?: string): HeadersInit {
  return {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
  };
}

export class SovereignRescueClient {
  constructor(
    private readonly baseUrl: string,
    private readonly fetcher: typeof fetch = fetch,
  ) {}

  async entitlement(): Promise<RescueEntitlement> {
    const response = await this.fetcher(endpoint(this.baseUrl, '/api/user/agent/rescue/entitlement'), {
      method: 'GET',
      credentials: 'include',
      headers: headers(),
    });
    const body = await responseObject(response);
    return body.entitlement as unknown as RescueEntitlement;
  }

  async diagnose(input: RequestInput): Promise<RescueDiagnosis> {
    const response = await this.fetcher(endpoint(this.baseUrl, '/api/user/agent/rescue/diagnose'), {
      method: 'POST',
      credentials: 'include',
      headers: headers(),
      body: JSON.stringify(input),
    });
    const body = await responseObject(response);
    return body.diagnosis as unknown as RescueDiagnosis;
  }

  async repair(
    input: RequestInput & { readonly expectedBaseSha: string },
    idempotencyKey: string,
  ): Promise<RescueRepair> {
    const response = await this.fetcher(endpoint(this.baseUrl, '/api/user/agent/rescue/repair'), {
      method: 'POST',
      credentials: 'include',
      headers: headers(idempotencyKey),
      body: JSON.stringify(input),
    });
    const body = await responseObject(response);
    return body.repair as unknown as RescueRepair;
  }

  async proofPack(repairId: string): Promise<RescueProofPack> {
    const response = await this.fetcher(
      endpoint(this.baseUrl, `/api/user/agent/rescue/repairs/${encodeURIComponent(repairId)}/proof-pack`),
      {
        method: 'POST',
        credentials: 'include',
        headers: headers(),
        body: JSON.stringify({}),
      },
    );
    const body = await responseObject(response);
    return body.proofPack as unknown as RescueProofPack;
  }
}

export function createSovereignRescueClient(baseUrl: string): SovereignRescueClient {
  return new SovereignRescueClient(baseUrl);
}
