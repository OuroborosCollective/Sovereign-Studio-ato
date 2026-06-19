import { buildGitHubHeaders, requireGitHubToken, stripTokenFromText } from './githubAuthSession';
import { parseGithubRepoUrl } from './utils';

export interface PublishableFile {
  path: string;
  content: string;
  reason?: string;
}

export interface PublishPackageInput {
  repoUrl: string;
  token: string;
  baseBranch?: string;
  title: string;
  body: string;
  files: PublishableFile[];
  branchPrefix?: string;
  branchNonce?: string;
  maxBranchAttempts?: number;
  maxRetries?: number;
  fetcher?: typeof fetch;
}

export interface PublishPackageResult {
  branch: string;
  baseBranch: string;
  commitSha: string;
  pullRequestNumber: number;
  pullRequestUrl: string;
}

interface GitHubRepoResponse {
  default_branch?: string;
}

interface GitHubRefResponse {
  object?: { sha?: string };
}

interface GitHubCommitResponse {
  tree?: { sha?: string };
}

interface GitHubTreeResponse {
  sha?: string;
}

interface GitHubPullResponse {
  number?: number;
  html_url?: string;
}

const FORBIDDEN_PATH_PREFIXES = ['.git/', 'node_modules/', 'dist/', 'build/'];
const FORBIDDEN_EXACT_PATHS = ['.env', '.env.local', '.env.production'];
const AUDIT_ONLY_PATH = 'generated/sovereign-product/workflow.ts';
const DEFAULT_MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 8000;

function isRetryableStatus(status: number): boolean {
  return status === 408 || status === 429 || status >= 500;
}

function computeRetryDelay(attempt: number, token: string): number {
  const exponentialDelay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt);
  const jitter = Math.random() * 500;
  const tokenHash = token.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const deterministicJitter = (tokenHash % 1000) / 1000 * 200;
  return Math.min(exponentialDelay + jitter + deterministicJitter, MAX_RETRY_DELAY_MS);
}

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function encodeBranchPath(branch: string): string {
  return branch.split('/').map(encodeURIComponent).join('/');
}

function normalizePath(path: string): string {
  return path.trim().replace(/^\/+/, '');
}

export function validatePublishableFiles(files: PublishableFile[]): PublishableFile[] {
  if (!files.length) throw new Error('No files to publish.');

  const seen = new Set<string>();
  const normalized = files.map((file) => {
    const path = normalizePath(file.path);
    const lower = path.toLowerCase();

    if (!path || path.includes('..') || path.startsWith('/')) {
      throw new Error(`Invalid publish path: ${file.path}`);
    }
    if (FORBIDDEN_EXACT_PATHS.includes(lower) || FORBIDDEN_PATH_PREFIXES.some((prefix) => lower.startsWith(prefix))) {
      throw new Error(`Refusing to publish forbidden path: ${path}`);
    }
    if (!file.content.trim()) {
      throw new Error(`Refusing to publish empty file: ${path}`);
    }
    if (seen.has(path)) {
      throw new Error(`Duplicate publish path: ${path}`);
    }
    seen.add(path);

    return { ...file, path };
  });

  // Reject single audit-only package
  if (normalized.length === 1 && normalized[0].path === AUDIT_ONLY_PATH) {
    throw new Error('Refusing to publish audit-only package. Publish requires multi-file content.');
  }

  return normalized;
}

async function githubJson<T>(
  fetcher: typeof fetch,
  url: string,
  token: string,
  init: RequestInit = {},
  options: { maxRetries?: number; retry?: number } = {},
): Promise<T> {
  const maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
  const attempt = options.retry ?? 0;

  try {
    const response = await fetcher(url, {
      ...init,
      headers: buildGitHubHeaders({ token, json: true, extra: init.headers }),
    });

    if (response.ok) {
      return response.json() as Promise<T>;
    }

    const message = await response.text().catch(() => '');

    if (attempt < maxRetries && isRetryableStatus(response.status)) {
      const delay = computeRetryDelay(attempt, token);
      await new Promise((resolve) => setTimeout(resolve, delay));
      return githubJson<T>(fetcher, url, token, init, { maxRetries, retry: attempt + 1 });
    }

    throw new Error(stripTokenFromText(`GitHub API ${response.status}: ${message || response.statusText}`, token));
  } catch (error) {
    if (attempt < maxRetries && error instanceof Error) {
      const isNetworkError = error.message.includes('fetch') || error.message.includes('network') || error.message.includes('ECONNREFUSED');
      if (isNetworkError) {
        const delay = computeRetryDelay(attempt, token);
        await new Promise((resolve) => setTimeout(resolve, delay));
        return githubJson<T>(fetcher, url, token, init, { maxRetries, retry: attempt + 1 });
      }
    }
    throw error;
  }
}

async function createUniqueBranchRef(
  fetcher: typeof fetch,
  apiBase: string,
  token: string,
  baseBranchName: string,
  baseSha: string,
  maxAttempts: number,
): Promise<string> {
  const attempts = Math.max(1, Math.min(maxAttempts, 20));

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const branch = attempt === 0 ? baseBranchName : `${baseBranchName}-${attempt + 1}`;
    const response = await fetcher(`${apiBase}/git/refs`, {
      method: 'POST',
      headers: buildGitHubHeaders({ token, json: true }),
      body: JSON.stringify({ ref: `refs/heads/${branch}`, sha: baseSha }),
    });

    if (response.ok) return branch;

    const message = await response.text().catch(() => '');
    if (response.status !== 422) {
      throw new Error(stripTokenFromText(`GitHub API ${response.status}: ${message || response.statusText}`, token));
    }
  }

  throw new Error(`Could not create a unique branch after ${attempts} attempts.`);
}

export function buildSovereignBranchName(prefix: string, title: string, files: PublishableFile[], nonce = ''): string {
  const source = `${title}\n${nonce}\n${files.map((file) => `${file.path}:${file.content.length}`).join('\n')}`;
  const cleanPrefix = prefix.toLowerCase().replace(/[^a-z0-9/_-]+/g, '-').replace(/^-+|-+$/g, '') || 'sovereign';
  return `${cleanPrefix}/${stableHash(source)}`;
}

export async function publishPackageAsDraftPr(input: PublishPackageInput): Promise<PublishPackageResult> {
  const parsed = parseGithubRepoUrl(input.repoUrl);
  if (!parsed) throw new Error('Invalid GitHub repository URL.');
  const token = requireGitHubToken(input.token, 'Draft PR publishing');

  const fetcher = input.fetcher ?? fetch;
  const files = validatePublishableFiles(input.files);
  const apiBase = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}`;
  const maxRetries = input.maxRetries ?? DEFAULT_MAX_RETRIES;

  const repo = await githubJson<GitHubRepoResponse>(fetcher, apiBase, token, {}, { maxRetries });
  const baseBranch = input.baseBranch?.trim() || repo.default_branch || 'main';
  const baseRef = await githubJson<GitHubRefResponse>(fetcher, `${apiBase}/git/ref/heads/${encodeBranchPath(baseBranch)}`, token, {}, { maxRetries });
  const baseSha = baseRef.object?.sha;
  if (!baseSha) throw new Error(`Could not resolve base branch: ${baseBranch}`);

  const baseCommit = await githubJson<GitHubCommitResponse>(fetcher, `${apiBase}/git/commits/${baseSha}`, token, {}, { maxRetries });
  const baseTreeSha = baseCommit.tree?.sha;
  if (!baseTreeSha) throw new Error('Could not resolve base tree.');

  const requestedBranch = buildSovereignBranchName(
    input.branchPrefix ?? 'sovereign/package',
    input.title,
    files,
    input.branchNonce ?? '',
  );
  const branch = await createUniqueBranchRef(
    fetcher,
    apiBase,
    token,
    requestedBranch,
    baseSha,
    input.maxBranchAttempts ?? 6,
  );

  const tree = await githubJson<GitHubTreeResponse>(fetcher, `${apiBase}/git/trees`, token, {
    method: 'POST',
    body: JSON.stringify({
      base_tree: baseTreeSha,
      tree: files.map((file) => ({
        path: file.path,
        mode: '100644',
        type: 'blob',
        content: file.content,
      })),
    }),
  }, { maxRetries });

  if (!tree.sha) throw new Error('Could not create GitHub tree.');

  const commit = await githubJson<{ sha?: string }>(fetcher, `${apiBase}/git/commits`, token, {
    method: 'POST',
    body: JSON.stringify({
      message: input.title,
      tree: tree.sha,
      parents: [baseSha],
    }),
  }, { maxRetries });

  if (!commit.sha) throw new Error('Could not create GitHub commit.');

  await githubJson(fetcher, `${apiBase}/git/refs/heads/${encodeBranchPath(branch)}`, token, {
    method: 'PATCH',
    body: JSON.stringify({ sha: commit.sha, force: false }),
  }, { maxRetries });

  const pr = await githubJson<GitHubPullResponse>(fetcher, `${apiBase}/pulls`, token, {
    method: 'POST',
    body: JSON.stringify({
      title: input.title,
      body: input.body,
      head: branch,
      base: baseBranch,
      draft: true,
      maintainer_can_modify: true,
    }),
  }, { maxRetries });

  if (!pr.number || !pr.html_url) throw new Error('GitHub did not return a pull request URL.');

  return {
    branch,
    baseBranch,
    commitSha: commit.sha,
    pullRequestNumber: pr.number,
    pullRequestUrl: pr.html_url,
  };
}
