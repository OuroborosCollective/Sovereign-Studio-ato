/** Cleanup is verified against GitHub; an HTTP acknowledgement is not absence. */
export interface CleanupReply { status: number; body: unknown }
export type CleanupGithub = (method: 'GET' | 'PATCH' | 'DELETE', path: string, data?: Record<string, unknown>) => Promise<CleanupReply>;
export interface CleanupScope {
  owner: string;
  repo: string;
  prNumber: number;
  headRef: string;
  markerPrefix: string;
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export async function verifyOwnedDraftCleanup(github: CleanupGithub, scope: CleanupScope) {
  const { owner, repo, prNumber, headRef, markerPrefix } = scope;
  if (!/^[A-Za-z0-9_.-]+$/.test(owner) || !/^[A-Za-z0-9_.-]+$/.test(repo)
    || !Number.isSafeInteger(prNumber) || prNumber < 1
    || !/^sovereign\/agent-[A-Za-z0-9/_-]+$/.test(headRef)
    || !/^\[live-vnext:[A-Za-z0-9-]+:$/.test(markerPrefix)) {
    throw new Error('LIVE_CLEANUP_SCOPE_INVALID');
  }
  const prefix = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;
  const prPath = `${prefix}/pulls/${prNumber}`;
  const refPath = `${prefix}/git/ref/heads/${headRef.split('/').map(encodeURIComponent).join('/')}`;
  const initial = await github('GET', prPath);
  const pr = record(initial.body);
  const head = record(pr.head);
  const base = record(pr.base);
  const headRepo = record(head.repo);
  const baseRepo = record(base.repo);
  const expectedRepository = `${owner}/${repo}`.toLowerCase();
  if (initial.status !== 200 || pr.number !== prNumber || pr.draft !== true || pr.merged_at !== null
    || !['open', 'closed'].includes(String(pr.state))
    || typeof pr.title !== 'string' || !pr.title.includes(markerPrefix)
    || head.ref !== headRef || typeof head.sha !== 'string' || !/^[0-9a-f]{40}$/.test(head.sha)
    || String(headRepo.full_name).toLowerCase() !== expectedRepository
    || String(baseRepo.full_name).toLowerCase() !== expectedRepository
    || !Number.isSafeInteger(headRepo.id) || Number(headRepo.id) < 1 || headRepo.id !== baseRepo.id) {
    throw new Error('LIVE_CLEANUP_OWNERSHIP_UNVERIFIED');
  }
  const expectedHeadSha = head.sha;
  if (pr.state === 'open') {
    const closed = await github('PATCH', prPath, { state: 'closed' });
    if (closed.status !== 200) throw new Error('LIVE_CLEANUP_CLOSE_REJECTED');
  }
  const closeReadback = await github('GET', prPath);
  const closedPr = record(closeReadback.body);
  const closedHead = record(closedPr.head);
  if (closeReadback.status !== 200 || closedPr.number !== prNumber || closedPr.state !== 'closed'
    || closedPr.draft !== true || closedPr.merged_at !== null
    || closedHead.ref !== headRef || closedHead.sha !== expectedHeadSha
    || record(closedHead.repo).id !== headRepo.id) {
    throw new Error('LIVE_CLEANUP_CLOSED_READBACK_FAILED');
  }
  const currentRef = await github('GET', refPath);
  if (currentRef.status === 404) {
    return { closed: true, branchDeleted: true, branchAbsenceStatus: 404, headSha: expectedHeadSha };
  }
  const ref = record(currentRef.body);
  const object = record(ref.object);
  if (currentRef.status !== 200 || ref.ref !== `refs/heads/${headRef}`
    || object.type !== 'commit' || object.sha !== expectedHeadSha) {
    throw new Error('LIVE_CLEANUP_BRANCH_REVISION_CHANGED');
  }
  const deleted = await github('DELETE', `${prefix}/git/refs/heads/${headRef.split('/').map(encodeURIComponent).join('/')}`);
  // In particular, 422 is a rejected request, never proof of deletion.
  if (deleted.status !== 204) throw new Error('LIVE_CLEANUP_DELETE_REJECTED');
  const absence = await github('GET', refPath);
  if (absence.status !== 404) throw new Error('LIVE_CLEANUP_BRANCH_ABSENCE_UNVERIFIED');
  return { closed: true, branchDeleted: true, branchAbsenceStatus: absence.status, headSha: expectedHeadSha };
}
