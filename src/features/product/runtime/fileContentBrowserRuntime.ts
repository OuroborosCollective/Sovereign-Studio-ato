/** Backend-owned workspace file preview. Browser-side GitHub content reads are forbidden. */
export type FileContentStatus = 'loaded' | 'too_large' | 'binary' | 'not_found' | 'error' | 'blocked';
export type FileLanguage = 'typescript' | 'javascript' | 'python' | 'rust' | 'go' | 'java' | 'css' | 'html' | 'json' | 'yaml' | 'toml' | 'markdown' | 'shell' | 'text' | 'unknown';
export interface FileContentResult { readonly status: FileContentStatus; readonly path: string; readonly content: string; readonly language: FileLanguage; readonly sizeBytes: number; readonly sha: string; readonly truncated: boolean; readonly error: string; }
export interface FileContentRequest { readonly jobId: string; readonly workspaceUsable?: boolean; readonly backendBase: string; readonly filePath: string; readonly repoOwner?: string; readonly repoName?: string; readonly repoRevision?: string; readonly repositoryReadScope?: string; readonly githubAccessToken?: string; readonly maxBytes?: number; readonly fetcher?: typeof fetch; }
export const MAX_PREVIEW_BYTES = 100_000;
const EXTENSIONS: Record<string, FileLanguage> = { '.ts':'typescript','.tsx':'typescript','.mts':'typescript','.cts':'typescript','.js':'javascript','.jsx':'javascript','.mjs':'javascript','.cjs':'javascript','.py':'python','.pyi':'python','.rs':'rust','.go':'go','.java':'java','.kt':'java','.kts':'java','.css':'css','.scss':'css','.sass':'css','.less':'css','.html':'html','.htm':'html','.svelte':'html','.vue':'html','.json':'json','.jsonc':'json','.yaml':'yaml','.yml':'yaml','.toml':'toml','.md':'markdown','.mdx':'markdown','.sh':'shell','.bash':'shell','.zsh':'shell','.fish':'shell','.txt':'text','.log':'text' };
const BINARY = new Set(['.png','.jpg','.jpeg','.gif','.svg','.ico','.webp','.avif','.woff','.woff2','.ttf','.otf','.eot','.zip','.tar','.gz','.bz2','.7z','.pdf','.docx','.xlsx','.pptx','.exe','.dll','.so','.dylib','.mp4','.mp3','.wav','.ogg','.pyc','.class','.o','.a']);
function extension(path: string): string { const index = path.toLowerCase().lastIndexOf('.'); return index < 0 ? '' : path.toLowerCase().slice(index); }
export function detectLanguage(path: string): FileLanguage { return EXTENSIONS[extension(path)] ?? 'unknown'; }
export function isBinaryPath(path: string): boolean { return BINARY.has(extension(path)); }
export function isPreviewable(path: string): boolean { return !isBinaryPath(path); }
function makeResult(path: string, status: FileContentStatus, error: string, extras: Partial<FileContentResult> = {}): FileContentResult { return { status, path, content: '', language: detectLanguage(path), sizeBytes: 0, sha: '', truncated: false, error, ...extras }; }
export async function fetchFileContent(request: FileContentRequest): Promise<FileContentResult> {
  const path = request.filePath.trim().replace(/^\/+/, '');
  if (!path || path.includes('..')) return makeResult(path, 'blocked', 'A bounded relative repository path is required.');
  if (isBinaryPath(path)) return makeResult(path, 'binary', `Binary file preview is not supported: ${path}`);

  const maxBytes = Math.min(Math.max(request.maxBytes ?? MAX_PREVIEW_BYTES, 1), MAX_PREVIEW_BYTES);
  const base = request.backendBase.replace(/\/$/, '');
  const fetcher = request.fetcher ?? fetch;
  const jobId = request.workspaceUsable === false ? '' : request.jobId.trim();
  let response: Response;
  let source: 'workspace' | 'repository';

  try {
    if (jobId) {
      source = 'workspace';
      response = await fetcher(`${base}/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/file`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ mode: 'read', path, maxBytes }),
      });
    } else {
      const owner = request.repoOwner?.trim() ?? '';
      const repo = request.repoName?.trim() ?? '';
      const ref = request.repoRevision?.trim().toLowerCase() ?? '';
      if (!owner || !repo) {
        return makeResult(path, 'blocked', 'No workspace job or repository identity is available for file preview.');
      }
      if (!/^[0-9a-f]{40}$/.test(ref)) {
        return makeResult(path, 'blocked', 'Repository file preview requires the immutable 40-character snapshot revision.');
      }
      let scope = request.repositoryReadScope?.trim() ?? '';
      if (!scope) {
        const parentScopeResponse = await fetcher(`${base}/api/user/agent/github-access/scope`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            repository: `https://github.com/${owner}/${repo}`,
            branch: ref,
            expectedBaseSha: ref,
            purpose: 'github-access-validate',
            ...(request.githubAccessToken ? { githubAccessToken: request.githubAccessToken } : {}),
          }),
        });
        let parentScopeBody: Record<string, unknown> = {};
        try { parentScopeBody = await parentScopeResponse.json() as Record<string, unknown>; } catch { parentScopeBody = {}; }
        const parentScope = typeof parentScopeBody.scope === 'string' ? parentScopeBody.scope.trim() : '';
        if (
          !parentScopeResponse.ok
          || parentScopeBody.ok !== true
          || !parentScope
          || String(parentScopeBody.baseSha ?? '').toLowerCase() !== ref
          || String(parentScopeBody.purpose ?? '') !== 'github-access-validate'
        ) {
          return makeResult(
            path,
            parentScopeResponse.status === 401 || parentScopeResponse.status === 403 || parentScopeResponse.status === 422
              ? 'blocked'
              : 'error',
            String(parentScopeBody.error ?? '') || 'Repository validation scope could not be verified.',
          );
        }

        const validationResponse = await fetcher(`${base}/api/user/agent/github-access/validate`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            scope: parentScope,
            ...(request.githubAccessToken ? { githubAccessToken: request.githubAccessToken } : {}),
          }),
        });
        let validationBody: Record<string, unknown> = {};
        try { validationBody = await validationResponse.json() as Record<string, unknown>; } catch { validationBody = {}; }
        scope = typeof validationBody.repositoryReadScope === 'string'
          ? validationBody.repositoryReadScope.trim()
          : '';
        if (
          !validationResponse.ok
          || !scope
          || String(validationBody.repositoryRevision ?? '').toLowerCase() !== ref
        ) {
          return makeResult(
            path,
            validationResponse.status === 401 || validationResponse.status === 403 || validationResponse.status === 422
              ? 'blocked'
              : 'error',
            String(validationBody.error ?? '') || 'Repository read scope could not be derived from validated revision evidence.',
          );
        }
      }

      source = 'repository';
      response = await fetcher(`${base}/api/user/agent/repository/read-file`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          scope,
          owner,
          repo,
          path,
          ref,
          maxBytes,
          ...(request.githubAccessToken ? { githubAccessToken: request.githubAccessToken } : {}),
        }),
      });
    }
  } catch (error) {
    return makeResult(path, 'error', `Repository file request failed: ${error instanceof Error ? error.message : String(error)}`);
  }

  let body: Record<string, unknown> = {};
  try { body = await response.json() as Record<string, unknown>; } catch { body = {}; }
  if (source === 'repository') {
    const blocker = String(body.error ?? '');
    if (
      response.status === 422
      && body.code === 'repository_file_scope_unverified'
      && request.repositoryReadScope
    ) {
      return fetchFileContent({ ...request, repositoryReadScope: undefined });
    }
    if (response.status === 403) return makeResult(path, 'blocked', blocker || 'Repository file read was blocked.');
    if (response.status === 415 || body.status === 'binary') return makeResult(path, 'binary', blocker || 'Repository file is not supported UTF-8 text.');
    if (response.status === 404 || /not found/i.test(blocker)) return makeResult(path, 'not_found', blocker || `File not found: ${path}`);
    if (!response.ok) return makeResult(path, 'error', blocker || `Repository file read failed with HTTP ${response.status}.`);
    const expectedRevision = request.repoRevision?.trim().toLowerCase() ?? '';
    if (
      body.scopeVerified !== true
      || String(body.repositoryRevision ?? '').toLowerCase() !== expectedRevision
      || String(body.revision ?? '').toLowerCase() !== expectedRevision
    ) {
      return makeResult(path, 'error', 'Repository file read returned revision-drifted or unverified evidence.');
    }
    const content = typeof body.content === 'string' ? body.content : '';
    const originalBytes = Number(body.bytes ?? new TextEncoder().encode(content).length);
    const blobSha = String(body.sha ?? '').trim().toLowerCase();
    if (!/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(blobSha)) {
      return makeResult(path, 'error', 'Repository file read returned no valid immutable blob identity.');
    }
    const truncated = body.truncated === true || originalBytes > maxBytes || content.length > maxBytes;
    const visible = truncated ? `${content.slice(0, Math.floor(maxBytes * 0.9))}\n\n[... content truncated at preview boundary ...]` : content;
    return makeResult(path, 'loaded', '', {
      content: visible,
      sizeBytes: originalBytes,
      sha: blobSha,
      truncated,
    });
  }

  const tool = typeof body.tool === 'object' && body.tool !== null ? body.tool as Record<string, unknown> : body;
  const status = String(tool.status ?? '');
  const blocker = String(tool.blocker ?? body.error ?? tool.error ?? '');
  const metadata = typeof tool.metadata === 'object' && tool.metadata !== null ? tool.metadata as Record<string, unknown> : {};
  if (metadata.previewStatus === 'binary' || blocker === 'repository_file_binary_unsupported') {
    return makeResult(path, 'binary', blocker || 'Workspace file is not supported UTF-8 text.');
  }
  if (status === 'blocked' || response.status === 403) return makeResult(path, 'blocked', blocker || 'Workspace file read was blocked.');
  if (response.status === 404 || /not found/i.test(blocker)) return makeResult(path, 'not_found', blocker || `File not found: ${path}`);
  if (status !== 'done' && status !== 'ok') return makeResult(path, 'error', blocker || `Workspace file read failed with HTTP ${response.status}.`);
  const content = String(tool.stdout ?? tool.output ?? '');
  const sizeBytes = Number(metadata.bytes ?? new TextEncoder().encode(content).length);
  const truncated = sizeBytes > maxBytes;
  const visible = truncated ? `${content.slice(0, Math.floor(maxBytes * 0.9))}\n\n[... content truncated at preview boundary ...]` : content;
  return makeResult(path, 'loaded', '', { content: visible, sizeBytes, sha: String(metadata.sha256 ?? ''), truncated });
}
