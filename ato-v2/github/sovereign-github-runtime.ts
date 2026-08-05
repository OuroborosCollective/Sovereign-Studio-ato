import { createHash } from 'node:crypto';
import { Octokit } from '@octokit/rest';

export const SOVEREIGN_GITHUB_API_VERSION = '2022-11-28' as const;
export const SOVEREIGN_GITHUB_ADAPTER_REVISION = 'sovereign-github-octokit-rest.v1' as const;

export type SovereignGitHubVerdict =
  | 'SUCCEEDED_UNVERIFIED'
  | 'VERIFIED'
  | 'CONTRADICTED'
  | 'BLOCKED_BY_MISSING_EVIDENCE';

export type SovereignGitHubCapabilityId =
  | 'github.repository.read'
  | 'github.contents.read'
  | 'github.contents.write'
  | 'github.git.ref.read'
  | 'github.git.ref.write'
  | 'github.commit.create'
  | 'github.issue.read'
  | 'github.issue.list'
  | 'github.issue.create'
  | 'github.issue.update'
  | 'github.issue.comment.read'
  | 'github.issue.comment.create'
  | 'github.issue.label.add'
  | 'github.issue.label.remove'
  | 'github.pull.read'
  | 'github.pull.create_draft'
  | 'github.pull.review.request'
  | 'github.pull.merge'
  | 'github.actions.read'
  | 'github.actions.rerun'
  | 'github.artifact.read'
  | 'github.ruleset.read'
  | 'github.ruleset.write';

interface EndpointContract {
  readonly method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  readonly endpointId: string;
  readonly mutates: boolean;
  readonly highRisk?: boolean;
}

export const SOVEREIGN_GITHUB_CAPABILITY_MAP: Readonly<Record<SovereignGitHubCapabilityId, EndpointContract>> = Object.freeze({
  'github.repository.read': { method: 'GET', endpointId: 'repos.get', mutates: false },
  'github.contents.read': { method: 'GET', endpointId: 'repos.getContent', mutates: false },
  'github.contents.write': { method: 'PUT', endpointId: 'repos.createOrUpdateFileContents', mutates: true },
  'github.git.ref.read': { method: 'GET', endpointId: 'git.getRef', mutates: false },
  'github.git.ref.write': { method: 'PATCH', endpointId: 'git.updateRef', mutates: true, highRisk: true },
  'github.commit.create': { method: 'POST', endpointId: 'git.createCommit', mutates: true },
  'github.issue.read': { method: 'GET', endpointId: 'issues.get', mutates: false },
  'github.issue.list': { method: 'GET', endpointId: 'issues.listForRepo', mutates: false },
  'github.issue.create': { method: 'POST', endpointId: 'issues.create', mutates: true },
  'github.issue.update': { method: 'PATCH', endpointId: 'issues.update', mutates: true },
  'github.issue.comment.read': { method: 'GET', endpointId: 'issues.getComment', mutates: false },
  'github.issue.comment.create': { method: 'POST', endpointId: 'issues.createComment', mutates: true },
  'github.issue.label.add': { method: 'POST', endpointId: 'issues.addLabels', mutates: true },
  'github.issue.label.remove': { method: 'DELETE', endpointId: 'issues.removeLabel', mutates: true },
  'github.pull.read': { method: 'GET', endpointId: 'pulls.get', mutates: false },
  'github.pull.create_draft': { method: 'POST', endpointId: 'pulls.create', mutates: true },
  'github.pull.review.request': { method: 'POST', endpointId: 'pulls.requestReviewers', mutates: true },
  'github.pull.merge': { method: 'PUT', endpointId: 'pulls.merge', mutates: true, highRisk: true },
  'github.actions.read': { method: 'GET', endpointId: 'actions.getWorkflowRun', mutates: false },
  'github.actions.rerun': { method: 'POST', endpointId: 'actions.reRunWorkflow', mutates: true, highRisk: true },
  'github.artifact.read': { method: 'GET', endpointId: 'actions.getArtifact', mutates: false },
  'github.ruleset.read': { method: 'GET', endpointId: 'repos.getRepoRuleset', mutates: false },
  'github.ruleset.write': { method: 'PUT', endpointId: 'repos.updateRepoRuleset', mutates: true, highRisk: true },
});

export interface SovereignGitHubEvidenceContext {
  readonly runId: string;
  readonly workflowStep: string;
  readonly skillId: string;
  readonly manifestHash: string;
  readonly principalIdentityHash: string;
  readonly permissionReceiptHash: string;
  readonly expectedRepositoryRevision: string;
  readonly idempotencyKey: string;
}

export interface SovereignGitHubRequestV1 {
  readonly schemaVersion: 'sovereign-github-request.v1';
  readonly capabilityId: SovereignGitHubCapabilityId;
  readonly owner: string;
  readonly repository: string;
  readonly method: EndpointContract['method'];
  readonly endpointId: string;
  readonly pathParams: Readonly<Record<string, string | number>>;
  readonly queryHash?: string;
  readonly bodyHash?: string;
  readonly expectedRepositoryRevision?: string;
  readonly expectedResourceVersion?: string;
  readonly idempotencyKey?: string;
  readonly permissionReceiptHash?: string;
}

export interface SovereignGitHubExecutionReceiptV1 {
  readonly schemaVersion: 'sovereign-github-execution-receipt.v1';
  readonly runId: string;
  readonly workflowStep: string;
  readonly skillId: string;
  readonly manifestHash: string;
  readonly capabilityId: SovereignGitHubCapabilityId;
  readonly adapterRevision: typeof SOVEREIGN_GITHUB_ADAPTER_REVISION;
  readonly apiVersion: typeof SOVEREIGN_GITHUB_API_VERSION;
  readonly principalIdentityHash: string;
  readonly repositoryIdentity: string;
  readonly requestHash: string;
  readonly permissionReceiptHash: string;
  readonly responseStatus: number;
  readonly responseHash: string;
  readonly expectedReadback: string;
  readonly verdict: SovereignGitHubVerdict;
}

export interface VerifiedDraftPullRequest {
  readonly number: number;
  readonly headSha: string;
  readonly transportReceipt: SovereignGitHubExecutionReceiptV1;
  readonly readbackReceipt: SovereignGitHubExecutionReceiptV1;
}

const HASH_PATTERN = /^[0-9a-f]{64}$/;
const REVISION_PATTERN = /^[0-9a-f]{40}$/;
const REPOSITORY_NAME_PATTERN = /^[A-Za-z0-9_.-]+$/;

function stableJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => item !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
    .join(',')}}`;
}

function digest(value: unknown): string {
  return createHash('sha256').update(typeof value === 'string' ? value : stableJson(value)).digest('hex');
}

function requireHash(value: string, label: string): void {
  if (!HASH_PATTERN.test(value)) throw new Error(`${label} must be a lowercase SHA-256 value`);
}

function requireEvidence(context: SovereignGitHubEvidenceContext): void {
  if (!context.runId || !context.workflowStep || !context.skillId || !context.idempotencyKey) {
    throw new Error('run, workflow, skill and idempotency identities are required');
  }
  requireHash(context.manifestHash, 'manifestHash');
  requireHash(context.principalIdentityHash, 'principalIdentityHash');
  requireHash(context.permissionReceiptHash, 'permissionReceiptHash');
  if (!REVISION_PATTERN.test(context.expectedRepositoryRevision)) {
    throw new Error('expectedRepositoryRevision must be a full commit SHA');
  }
}

function requestFor(input: {
  capabilityId: SovereignGitHubCapabilityId;
  owner: string;
  repository: string;
  pathParams: Readonly<Record<string, string | number>>;
  body?: unknown;
  evidence?: SovereignGitHubEvidenceContext;
  expectedResourceVersion?: string;
}): SovereignGitHubRequestV1 {
  const contract = SOVEREIGN_GITHUB_CAPABILITY_MAP[input.capabilityId];
  if (!REPOSITORY_NAME_PATTERN.test(input.owner) || !REPOSITORY_NAME_PATTERN.test(input.repository)) {
    throw new Error('owner and repository must be canonical identifiers');
  }
  if (Object.keys(input.pathParams).some((key) => ['url', 'endpoint', 'token', 'authorization'].includes(key.toLowerCase()))) {
    throw new Error('free URL and credential path parameters are forbidden');
  }
  if (contract.mutates) {
    if (!input.evidence) throw new Error('mutating GitHub requests require evidence context');
    requireEvidence(input.evidence);
  }
  return Object.freeze({
    schemaVersion: 'sovereign-github-request.v1',
    capabilityId: input.capabilityId,
    owner: input.owner,
    repository: input.repository,
    method: contract.method,
    endpointId: contract.endpointId,
    pathParams: Object.freeze({ ...input.pathParams }),
    ...(input.body === undefined ? {} : { bodyHash: digest(input.body) }),
    ...(input.evidence ? {
      expectedRepositoryRevision: input.evidence.expectedRepositoryRevision,
      idempotencyKey: input.evidence.idempotencyKey,
      permissionReceiptHash: input.evidence.permissionReceiptHash,
    } : {}),
    ...(input.expectedResourceVersion ? { expectedResourceVersion: input.expectedResourceVersion } : {}),
  });
}

function receipt(input: {
  context: SovereignGitHubEvidenceContext;
  capabilityId: SovereignGitHubCapabilityId;
  owner: string;
  repository: string;
  request: SovereignGitHubRequestV1;
  responseStatus: number;
  response: unknown;
  expectedReadback: string;
  verdict: SovereignGitHubVerdict;
}): SovereignGitHubExecutionReceiptV1 {
  return Object.freeze({
    schemaVersion: 'sovereign-github-execution-receipt.v1',
    runId: input.context.runId,
    workflowStep: input.context.workflowStep,
    skillId: input.context.skillId,
    manifestHash: input.context.manifestHash,
    capabilityId: input.capabilityId,
    adapterRevision: SOVEREIGN_GITHUB_ADAPTER_REVISION,
    apiVersion: SOVEREIGN_GITHUB_API_VERSION,
    principalIdentityHash: input.context.principalIdentityHash,
    repositoryIdentity: `${input.owner}/${input.repository}`,
    requestHash: digest(input.request),
    permissionReceiptHash: input.context.permissionReceiptHash,
    responseStatus: input.responseStatus,
    responseHash: digest(input.response),
    expectedReadback: input.expectedReadback,
    verdict: input.verdict,
  });
}

function loadServerToken(): string {
  if (typeof window !== 'undefined') {
    throw new Error('Sovereign GitHub operator credentials are forbidden in browser and mobile runtimes');
  }
  const token = process.env.GITHUB_TOKEN?.trim();
  if (!token) throw new Error('GITHUB_TOKEN is required in the server/operator environment');
  return token;
}

function buildOctokit(token?: string): Octokit {
  return new Octokit({
    ...(token ? { auth: token } : {}),
    baseUrl: 'https://api.github.com',
    request: { headers: { 'X-GitHub-Api-Version': SOVEREIGN_GITHUB_API_VERSION } },
  });
}

export async function readPublicRepository(owner: string, repository: string): Promise<{
  readonly fullName: string;
  readonly defaultBranch: string;
  readonly responseHash: string;
}> {
  const request = requestFor({
    capabilityId: 'github.repository.read',
    owner,
    repository,
    pathParams: { owner, repository },
  });
  const { data } = await buildOctokit().rest.repos.get({ owner, repo: repository });
  return Object.freeze({
    fullName: data.full_name,
    defaultBranch: data.default_branch,
    responseHash: digest({ request, id: data.id, full_name: data.full_name, default_branch: data.default_branch }),
  });
}

export class SovereignGitHubRuntime {
  private readonly octokit: Octokit;

  constructor(token = loadServerToken()) {
    this.octokit = buildOctokit(token);
  }

  async createDraftPullRequest(input: {
    readonly owner: string;
    readonly repository: string;
    readonly title: string;
    readonly head: string;
    readonly base: string;
    readonly body: string;
    readonly evidence: SovereignGitHubEvidenceContext;
  }): Promise<VerifiedDraftPullRequest> {
    const body = {
      title: input.title,
      head: input.head,
      base: input.base,
      body: input.body,
      draft: true,
      maintainer_can_modify: true,
    };
    const request = requestFor({
      capabilityId: 'github.pull.create_draft',
      owner: input.owner,
      repository: input.repository,
      pathParams: { head: input.head, base: input.base },
      body,
      evidence: input.evidence,
    });
    const created = await this.octokit.rest.pulls.create({
      owner: input.owner,
      repo: input.repository,
      ...body,
    });
    const transportReceipt = receipt({
      context: input.evidence,
      capabilityId: 'github.pull.create_draft',
      owner: input.owner,
      repository: input.repository,
      request,
      responseStatus: created.status,
      response: { number: created.data.number, id: created.data.id, headSha: created.data.head.sha },
      expectedReadback: 'pulls.get must confirm number, draft state, head, base and head SHA',
      verdict: 'SUCCEEDED_UNVERIFIED',
    });

    const readback = await this.octokit.rest.pulls.get({
      owner: input.owner,
      repo: input.repository,
      pull_number: created.data.number,
    });
    const verified = readback.data.number === created.data.number
      && readback.data.head.ref === input.head
      && readback.data.base.ref === input.base
      && readback.data.draft === true
      && readback.data.head.sha === created.data.head.sha;
    const readbackRequest = requestFor({
      capabilityId: 'github.pull.read',
      owner: input.owner,
      repository: input.repository,
      pathParams: { pull_number: created.data.number },
    });
    const readbackReceipt = receipt({
      context: input.evidence,
      capabilityId: 'github.pull.read',
      owner: input.owner,
      repository: input.repository,
      request: readbackRequest,
      responseStatus: readback.status,
      response: {
        number: readback.data.number,
        draft: readback.data.draft,
        head: readback.data.head.ref,
        headSha: readback.data.head.sha,
        base: readback.data.base.ref,
      },
      expectedReadback: 'independent pull readback completed',
      verdict: verified ? 'VERIFIED' : 'CONTRADICTED',
    });
    if (!verified) throw new Error('GitHub draft PR readback contradicted the requested effect');
    return Object.freeze({
      number: created.data.number,
      headSha: created.data.head.sha,
      transportReceipt,
      readbackReceipt,
    });
  }

  async addLabels(input: {
    readonly owner: string;
    readonly repository: string;
    readonly issueNumber: number;
    readonly labels: readonly string[];
    readonly evidence: SovereignGitHubEvidenceContext;
  }): Promise<SovereignGitHubExecutionReceiptV1> {
    const labels = Array.from(new Set(input.labels.map((label) => label.trim()).filter(Boolean))).sort();
    const request = requestFor({
      capabilityId: 'github.issue.label.add',
      owner: input.owner,
      repository: input.repository,
      pathParams: { issue_number: input.issueNumber },
      body: { labels },
      evidence: input.evidence,
      expectedResourceVersion: String(input.issueNumber),
    });
    const response = await this.octokit.rest.issues.addLabels({
      owner: input.owner,
      repo: input.repository,
      issue_number: input.issueNumber,
      labels,
    });
    const observed = response.data.map((label) => label.name).filter(Boolean).sort();
    const verified = labels.every((label) => observed.includes(label));
    return receipt({
      context: input.evidence,
      capabilityId: 'github.issue.label.add',
      owner: input.owner,
      repository: input.repository,
      request,
      responseStatus: response.status,
      response: { observed },
      expectedReadback: 'issues.addLabels response projection confirms requested labels; later PR readback remains authoritative',
      verdict: verified ? 'VERIFIED' : 'CONTRADICTED',
    });
  }

  async requestReviewers(input: {
    readonly owner: string;
    readonly repository: string;
    readonly pullNumber: number;
    readonly reviewers: readonly string[];
    readonly evidence: SovereignGitHubEvidenceContext;
  }): Promise<SovereignGitHubExecutionReceiptV1> {
    const reviewers = Array.from(new Set(input.reviewers.map((reviewer) => reviewer.trim()).filter(Boolean))).sort();
    const request = requestFor({
      capabilityId: 'github.pull.review.request',
      owner: input.owner,
      repository: input.repository,
      pathParams: { pull_number: input.pullNumber },
      body: { reviewers },
      evidence: input.evidence,
      expectedResourceVersion: String(input.pullNumber),
    });
    const response = await this.octokit.rest.pulls.requestReviewers({
      owner: input.owner,
      repo: input.repository,
      pull_number: input.pullNumber,
      reviewers,
    });
    const observed = response.data.requested_reviewers?.map((reviewer) => reviewer.login).filter(Boolean).sort() ?? [];
    const verified = reviewers.every((reviewer) => observed.includes(reviewer));
    return receipt({
      context: input.evidence,
      capabilityId: 'github.pull.review.request',
      owner: input.owner,
      repository: input.repository,
      request,
      responseStatus: response.status,
      response: { observed },
      expectedReadback: 'requested reviewer projection must contain every requested login',
      verdict: verified ? 'VERIFIED' : 'CONTRADICTED',
    });
  }

  async listIssueSignals(input: {
    readonly owner: string;
    readonly repository: string;
    readonly state?: 'open' | 'closed' | 'all';
    readonly labels?: readonly string[];
    readonly since?: string;
  }): Promise<readonly {
    readonly id: number;
    readonly title: string;
    readonly body: string;
    readonly number: number;
    readonly labels: readonly string[];
    readonly url: string;
    readonly state: string;
    readonly createdAt: string;
    readonly updatedAt: string;
    readonly responseHash: string;
  }[]> {
    const request = requestFor({
      capabilityId: 'github.issue.list',
      owner: input.owner,
      repository: input.repository,
      pathParams: { owner: input.owner, repository: input.repository },
    });
    const response = await this.octokit.rest.issues.listForRepo({
      owner: input.owner,
      repo: input.repository,
      state: input.state ?? 'open',
      labels: input.labels?.join(',') || 'autonomous-task',
      since: input.since,
      sort: 'updated',
      direction: 'desc',
      per_page: 100,
    });
    return Object.freeze(response.data
      .filter((issue) => !('pull_request' in issue))
      .map((issue) => Object.freeze({
        id: issue.id,
        title: issue.title,
        body: issue.body ?? '',
        number: issue.number,
        labels: Object.freeze((issue.labels ?? [])
          .map((label) => typeof label === 'string' ? label : label.name ?? '')
          .filter(Boolean)
          .sort()),
        url: issue.html_url,
        state: issue.state,
        createdAt: issue.created_at,
        updatedAt: issue.updated_at,
        responseHash: digest({ request, id: issue.id, updated_at: issue.updated_at }),
      })));
  }

  async createIssueComment(input: {
    readonly owner: string;
    readonly repository: string;
    readonly issueNumber: number;
    readonly body: string;
    readonly evidence: SovereignGitHubEvidenceContext;
  }): Promise<SovereignGitHubExecutionReceiptV1> {
    const request = requestFor({
      capabilityId: 'github.issue.comment.create',
      owner: input.owner,
      repository: input.repository,
      pathParams: { issue_number: input.issueNumber },
      body: { body: input.body },
      evidence: input.evidence,
      expectedResourceVersion: String(input.issueNumber),
    });
    const created = await this.octokit.rest.issues.createComment({
      owner: input.owner,
      repo: input.repository,
      issue_number: input.issueNumber,
      body: input.body,
    });
    const readback = await this.octokit.rest.issues.getComment({
      owner: input.owner,
      repo: input.repository,
      comment_id: created.data.id,
    });
    const verified = readback.data.id === created.data.id && readback.data.body === input.body;
    return receipt({
      context: input.evidence,
      capabilityId: 'github.issue.comment.create',
      owner: input.owner,
      repository: input.repository,
      request,
      responseStatus: readback.status,
      response: { id: readback.data.id, bodyHash: digest(readback.data.body ?? '') },
      expectedReadback: 'issues.getComment must confirm comment identity and body hash',
      verdict: verified ? 'VERIFIED' : 'CONTRADICTED',
    });
  }

  async removeLabel(input: {
    readonly owner: string;
    readonly repository: string;
    readonly issueNumber: number;
    readonly label: string;
    readonly evidence: SovereignGitHubEvidenceContext;
  }): Promise<SovereignGitHubExecutionReceiptV1> {
    const request = requestFor({
      capabilityId: 'github.issue.label.remove',
      owner: input.owner,
      repository: input.repository,
      pathParams: { issue_number: input.issueNumber, name: input.label },
      body: { label: input.label },
      evidence: input.evidence,
      expectedResourceVersion: String(input.issueNumber),
    });
    let responseStatus = 200;
    try {
      const removed = await this.octokit.rest.issues.removeLabel({
        owner: input.owner,
        repo: input.repository,
        issue_number: input.issueNumber,
        name: input.label,
      });
      responseStatus = removed.status;
    } catch (error: unknown) {
      const status = typeof error === 'object' && error !== null && 'status' in error
        ? Number((error as { status?: unknown }).status)
        : 0;
      if (status !== 404) throw error;
      responseStatus = status;
    }
    const readback = await this.octokit.rest.issues.get({
      owner: input.owner,
      repo: input.repository,
      issue_number: input.issueNumber,
    });
    const observed = (readback.data.labels ?? [])
      .map((label) => typeof label === 'string' ? label : label.name ?? '')
      .filter(Boolean);
    const verified = !observed.includes(input.label);
    return receipt({
      context: input.evidence,
      capabilityId: 'github.issue.label.remove',
      owner: input.owner,
      repository: input.repository,
      request,
      responseStatus,
      response: { observed: observed.sort() },
      expectedReadback: 'issues.get must confirm the removed label is absent',
      verdict: verified ? 'VERIFIED' : 'CONTRADICTED',
    });
  }
}

export function createSovereignGitHubRuntime(): SovereignGitHubRuntime {
  return new SovereignGitHubRuntime();
}
