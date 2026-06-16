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
  return files.map((file) => {
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
}

async function githubJson<T>(fetcher: typeof fetch, url: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetcher(url, {
    ...init,
    headers: {
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2022-11-28',
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await response.text().catch(() => '');
    throw new Error(`GitHub API ${response.status}: ${message || response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export function buildSovereignBranchName(prefix: string, title: string, files: PublishableFile[]): string {
  const source = `${title}\n${files.map((file) => `${file.path}:${file.content.length}`).join('\n')}`;
  const cleanPrefix = prefix.toLowerCase().replace(/[^a-z0-9/_-]+/g, '-').replace(/^-+|-+$/g, '') || 'sovereign';
  return `${cleanPrefix}/${stableHash(source)}`;
}

export async function publishPackageAsDraftPr(input: PublishPackageInput): Promise<PublishPackageResult> {
  const parsed = parseGithubRepoUrl(input.repoUrl);
  if (!parsed) throw new Error('Invalid GitHub repository URL.');
  if (!input.token.trim()) throw new Error('GitHub token is required to create a draft PR.');

  const fetcher = input.fetcher ?? fetch;
  const files = validatePublishableFiles(input.files);
  const apiBase = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}`;

  const repo = await githubJson<GitHubRepoResponse>(fetcher, apiBase, input.token);
  const baseBranch = input.baseBranch?.trim() || repo.default_branch || 'main';
  const baseRef = await githubJson<GitHubRefResponse>(fetcher, `${apiBase}/git/ref/heads/${encodeBranchPath(baseBranch)}`, input.token);
  const baseSha = baseRef.object?.sha;
  if (!baseSha) throw new Error(`Could not resolve base branch: ${baseBranch}`);

  const baseCommit = await githubJson<GitHubCommitResponse>(fetcher, `${apiBase}/git/commits/${baseSha}`, input.token);
  const baseTreeSha = baseCommit.tree?.sha;
  if (!baseTreeSha) throw new Error('Could not resolve base tree.');

  const branch = buildSovereignBranchName(input.branchPrefix ?? 'sovereign/package', input.title, files);

  await githubJson(fetcher, `${apiBase}/git/refs`, input.token, {
    method: 'POST',
    body: JSON.stringify({ ref: `refs/heads/${branch}`, sha: baseSha }),
  });

  const tree = await githubJson<GitHubTreeResponse>(fetcher, `${apiBase}/git/trees`, input.token, {
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
  });

  if (!tree.sha) throw new Error('Could not create GitHub tree.');

  const commit = await githubJson<{ sha?: string }>(fetcher, `${apiBase}/git/commits`, input.token, {
    method: 'POST',
    body: JSON.stringify({
      message: input.title,
      tree: tree.sha,
      parents: [baseSha],
    }),
  });

  if (!commit.sha) throw new Error('Could not create GitHub commit.');

  await githubJson(fetcher, `${apiBase}/git/refs/heads/${encodeBranchPath(branch)}`, input.token, {
    method: 'PATCH',
    body: JSON.stringify({ sha: commit.sha, force: false }),
  });

  const pr = await githubJson<GitHubPullResponse>(fetcher, `${apiBase}/pulls`, input.token, {
    method: 'POST',
    body: JSON.stringify({
      title: input.title,
      body: input.body,
      head: branch,
      base: baseBranch,
      draft: true,
      maintainer_can_modify: true,
    }),
  });

  if (!pr.number || !pr.html_url) throw new Error('GitHub did not return a pull request URL.');

  return {
    branch,
    baseBranch,
    commitSha: commit.sha,
    pullRequestNumber: pr.number,
    pullRequestUrl: pr.html_url,
  };
}
