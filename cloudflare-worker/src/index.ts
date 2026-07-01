/**
 * Sovereign Studio - Cloudflare Worker
 * 
 * Endpoints:
 * - GET /health - Health check
 * - GET /cache/:key - Get cached response
 * - PUT /cache/:key - Set cached response
 * - DELETE /cache/:key - Invalidate cache entry
 * - POST /git/patch - Apply SEARCH/REPLACE blocks and create Draft PR
 */

interface Env {
  CACHE?: KVNamespace;
  ANALYTICS?: AnalyticsEngineDataset;
  CACHE_TTL_SECONDS: string;
  GITHUB_TOKEN: string;
}

// CORS headers for frontend access
const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

const DEFAULT_TTL = 1800; // 30 minutes in seconds

// Forbidden path prefixes for security
const FORBIDDEN_PATHS = ['.git/', 'node_modules/', 'dist/', 'build/', '.env'];

interface PatchBlock {
  search: string;
  replace: string;
}

interface GitPatchRequest {
  owner: string;
  repo: string;
  path: string;
  message: string;
  blocks: PatchBlock[];
  branchPrefix?: string;
}

interface GitHubContentsResponse {
  content?: string;
  sha?: string;
  encoding?: string;
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

interface GitHubPRResponse {
  number?: number;
  html_url?: string;
}

// Strip base64 encoding from GitHub contents
function decodeBase64Content(encoded: string): string {
  // GitHub returns content with newlines every 76 characters
  const cleaned = encoded.replace(/\n/g, '');
  try {
    return atob(cleaned);
  } catch {
    return encoded;
  }
}

// Count exact occurrences of search string in content
function countMatches(content: string, search: string): number {
  if (!search) return 0;
  let count = 0;
  let index = 0;
  while ((index = content.indexOf(search, index)) !== -1) {
    count++;
    index += search.length;
  }
  return count;
}

// Apply SEARCH/REPLACE blocks to content (exits on 0 or >1 match)
function applyPatchBlocks(content: string, blocks: PatchBlock[]): { success: boolean; result?: string; error?: string; failedBlock?: number } {
  let result = content;
  
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    const matchCount = countMatches(result, block.search);
    
    if (matchCount === 0) {
      return { success: false, error: `Block ${i + 1}: SEARCH string not found`, failedBlock: i };
    }
    if (matchCount > 1) {
      return { success: false, error: `Block ${i + 1}: SEARCH string found ${matchCount} times (expected exactly 1)`, failedBlock: i };
    }
    
    result = result.replace(block.search, block.replace);
  }
  
  return { success: true, result };
}

// Build stable branch name from content hash
function buildBranchName(prefix: string, path: string, content: string): string {
  const source = `${path}:${content.length}:${content.substring(0, 100)}`;
  let hash = 0x811c9dc5;
  for (let i = 0; i < source.length; i++) {
    hash ^= source.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  const shortHash = (hash >>> 0).toString(16).substring(0, 8);
  const safePrefix = prefix.toLowerCase().replace(/[^a-z0-9/-]+/g, '-').replace(/^-|-$/g, '') || 'patch';
  return `${safePrefix}/${shortHash}`;
}

// GitHub API helper with retry logic
async function githubFetch<T>(
  url: string,
  token: string,
  options: RequestInit = {},
  retries = 3
): Promise<T> {
  for (let attempt = 0; attempt < retries; attempt++) {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'Sovereign-Studio-Worker/1.0',
        ...options.headers,
      },
    });
    
    if (response.ok) {
      return response.json() as Promise<T>;
    }
    
    // Retry on rate limit or server errors
    if (response.status === 429 || response.status >= 500) {
      const retryAfter = response.headers.get('Retry-After');
      await new Promise(r => setTimeout(r, retryAfter ? parseInt(retryAfter) * 1000 : 1000 * (attempt + 1)));
      continue;
    }
    
    const error = await response.text().catch(() => response.statusText);
    throw new Error(`GitHub API ${response.status}: ${error}`);
  }
  
  throw new Error('Max retries exceeded');
}

// Simple hash for cache key validation
function isValidKey(key: string): boolean {
  return /^[a-z0-9_]{1,128}$/.test(key);
}

// Validate path is safe for modification
function isPathSafe(path: string): boolean {
  const lower = path.toLowerCase();
  return !FORBIDDEN_PATHS.some(prefix => lower.startsWith(prefix));
}

// Handle POST /git/patch
async function handleGitPatch(request: Request, env: Env): Promise<Response> {
  // Get token from env or Authorization header
  const authHeader = request.headers.get('Authorization');
  const token = authHeader?.startsWith('Bearer ') 
    ? authHeader.substring(7) 
    : env.GITHUB_TOKEN;
  
  if (!token) {
    return jsonResponse({ error: 'GitHub token required' }, 401);
  }

  // Parse request body
  let body: GitPatchRequest;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'Invalid JSON body' }, 400);
  }

  // Validate required fields
  if (!body.owner || !body.repo || !body.path || !body.blocks?.length) {
    return jsonResponse({ error: 'Missing required fields: owner, repo, path, blocks' }, 400);
  }

  // Validate path safety
  if (!isPathSafe(body.path)) {
    return jsonResponse({ error: `Path not allowed: ${body.path}` }, 403);
  }

  const apiBase = `https://api.github.com/repos/${body.owner}/${body.repo}`;

  try {
    // 1. Get current file content
    const contents = await githubFetch<GitHubContentsResponse>(
      `${apiBase}/contents/${body.path}`,
      token
    );

    if (!contents.content) {
      return jsonResponse({ error: 'File not found or empty' }, 404);
    }

    const currentContent = decodeBase64Content(contents.content);
    const fileSha = contents.sha;

    // 2. Apply patch blocks (exits on 0 or >1 match)
    const patchResult = applyPatchBlocks(currentContent, body.blocks);
    if (!patchResult.success || !patchResult.result) {
      return jsonResponse({ 
        error: 'Patch failed', 
        details: patchResult.error,
        failedBlock: patchResult.failedBlock
      }, 422);
    }

    // 3. Get base branch SHA
    const repoInfo = await githubFetch<{ default_branch: string }>(
      apiBase,
      token
    );
    const baseBranch = 'main'; // Could be configurable
    const baseRef = await githubFetch<GitHubRefResponse>(
      `${apiBase}/git/refs/heads/${baseBranch}`,
      token
    );
    const baseSha = baseRef.object?.sha;
    if (!baseSha) {
      return jsonResponse({ error: 'Could not resolve base branch' }, 500);
    }

    // 4. Get base tree SHA
    const baseCommit = await githubFetch<GitHubCommitResponse>(
      `${apiBase}/git/commits/${baseSha}`,
      token
    );
    const baseTreeSha = baseCommit.tree?.sha;
    if (!baseTreeSha) {
      return jsonResponse({ error: 'Could not resolve base tree' }, 500);
    }

    // 5. Build stable branch name
    const branchPrefix = body.branchPrefix || 'sovereign/patch';
    const branch = buildBranchName(branchPrefix, body.path, patchResult.result);

    // 6. Create branch (with collision handling)
    let createdBranch = branch;
    for (let attempt = 0; attempt < 10; attempt++) {
      const branchName = attempt === 0 ? createdBranch : `${createdBranch}-${attempt}`;
      try {
        await githubFetch(`${apiBase}/git/refs`, token, {
          method: 'POST',
          body: JSON.stringify({ ref: `refs/heads/${branchName}`, sha: baseSha }),
        });
        createdBranch = branchName;
        break;
      } catch (e) {
        if (attempt === 9) throw e;
        // Branch exists, try next suffix
      }
    }

    // 7. Create tree with updated file
    const newTree = await githubFetch<GitHubTreeResponse>(`${apiBase}/git/trees`, token, {
      method: 'POST',
      body: JSON.stringify({
        base_tree: baseTreeSha,
        tree: [{
          path: body.path,
          mode: '100644',
          type: 'blob',
          content: patchResult.result,
        }],
      }),
    });
    if (!newTree.sha) {
      return jsonResponse({ error: 'Could not create tree' }, 500);
    }

    // 8. Create commit
    const commitMessage = body.message || `Patch: ${body.path}`;
    const newCommit = await githubFetch<{ sha?: string }>(`${apiBase}/git/commits`, token, {
      method: 'POST',
      body: JSON.stringify({
        message: commitMessage,
        tree: newTree.sha,
        parents: [baseSha],
      }),
    });
    if (!newCommit.sha) {
      return jsonResponse({ error: 'Could not create commit' }, 500);
    }

    // 9. Update branch ref
    await githubFetch(`${apiBase}/git/refs/heads/${createdBranch}`, token, {
      method: 'PATCH',
      body: JSON.stringify({ sha: newCommit.sha }),
    });

    // 10. Create Draft PR
    const pr = await githubFetch<GitHubPRResponse>(`${apiBase}/pulls`, token, {
      method: 'POST',
      body: JSON.stringify({
        title: commitMessage,
        body: `## Patch Applied\n\nFile: \`${body.path}\`\nBlocks: ${body.blocks.length}\n\n---\n*Created by Sovereign Studio Patch Worker*`,
        head: createdBranch,
        base: baseBranch,
        draft: true,
      }),
    });

    return jsonResponse({
      ok: true,
      branch: createdBranch,
      commit: newCommit.sha,
      pr: pr.number,
      prUrl: pr.html_url,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return jsonResponse({ error: 'GitHub API error', details: message }, 500);
  }
}

// Helper for JSON responses with CORS
function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    // Health check endpoint
    if (path === '/health') {
      return jsonResponse({ ok: true, timestamp: Date.now() });
    }

    // Git patch endpoint
    if (path === '/git/patch' && request.method === 'POST') {
      return handleGitPatch(request, env);
    }

    // Cache operations
    const cacheMatch = path.match(/^\/cache\/([a-z0-9_]+)$/);
    if (cacheMatch) {
      const key = cacheMatch[1];
      if (!isValidKey(key)) {
        return jsonResponse({ error: 'Invalid cache key' }, 400);
      }

      const ttl = parseInt(env.CACHE_TTL_SECONDS || String(DEFAULT_TTL), 10) * 1000;

      switch (request.method) {
        case 'GET': {
          if (!env.CACHE) return jsonResponse({ error: 'Cache not configured' }, 503);
          const cached = await env.CACHE.get(key, 'json');
          return jsonResponse(cached ? { hit: true, data: cached } : { hit: false });
        }

        case 'PUT': {
          if (!env.CACHE) return jsonResponse({ error: 'Cache not configured' }, 503);
          try {
            const body = await request.json();
            await env.CACHE.put(key, JSON.stringify({ 
              metadata: { createdAt: Date.now(), ttl },
              data: body 
            }), {
              expirationTtl: Math.floor(ttl / 1000),
            });
            return jsonResponse({ ok: true, key });
          } catch {
            return jsonResponse({ error: 'Invalid JSON body' }, 400);
          }
        }

        case 'DELETE': {
          if (!env.CACHE) return jsonResponse({ error: 'Cache not configured' }, 503);
          await env.CACHE.delete(key);
          return jsonResponse({ ok: true, key });
        }
      }
    }

    return jsonResponse({ error: 'Not found' }, 404);
  },
};
