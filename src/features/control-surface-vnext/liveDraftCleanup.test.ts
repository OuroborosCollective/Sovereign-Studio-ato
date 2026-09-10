import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { verifyOwnedDraftCleanup, type CleanupGithub, type CleanupReply } from '../../../tests/e2e/helpers/live-draft-cleanup';

const scope = { owner: 'Example', repo: 'owned', prNumber: 9, headRef: 'sovereign/agent-owned', markerPrefix: '[live-vnext:123:' };
const sha = 'a'.repeat(40);
function pull(state = 'open') {
  const repo = { id: 42, full_name: 'Example/owned' };
  return { number: 9, title: '[live-vnext:123:p1] test', draft: true, merged_at: null, state, head: { ref: scope.headRef, sha, repo }, base: { repo } };
}
function sequence(responses: CleanupReply[]) {
  const calls: string[] = [];
  const github: CleanupGithub = async (method, path) => {
    calls.push(`${method} ${path}`);
    const result = responses.shift();
    if (!result) throw new Error('Unexpected GitHub call');
    return result;
  };
  return { github, calls };
}
function normal(deleteStatus = 204, absenceStatus = 404): CleanupReply[] {
  return [
    { status: 200, body: pull() }, { status: 200, body: pull('closed') },
    { status: 200, body: pull('closed') },
    { status: 200, body: { ref: `refs/heads/${scope.headRef}`, object: { type: 'commit', sha } } },
    { status: deleteStatus, body: null }, { status: absenceStatus, body: null },
  ];
}

describe('real live-path Draft-PR cleanup contract', () => {
  it('requires independent closed-PR and absent-branch readbacks', async () => {
    const { github, calls } = sequence(normal());
    await expect(verifyOwnedDraftCleanup(github, scope)).resolves.toMatchObject({ closed: true, branchDeleted: true, branchAbsenceStatus: 404, headSha: sha });
    expect(calls.map(call => call.split(' ')[0])).toEqual(['GET', 'PATCH', 'GET', 'GET', 'DELETE', 'GET']);
  });
  it.each([401, 403, 404, 409, 422, 500])('rejects deletion HTTP %i instead of accepting absence', async status => {
    await expect(verifyOwnedDraftCleanup(sequence(normal(status)).github, scope)).rejects.toThrow('LIVE_CLEANUP_DELETE_REJECTED');
  });
  it.each([200, 401, 403, 422, 500])('does not accept post-delete HTTP %i as absence', async status => {
    await expect(verifyOwnedDraftCleanup(sequence(normal(204, status)).github, scope)).rejects.toThrow('LIVE_CLEANUP_BRANCH_ABSENCE_UNVERIFIED');
  });
  it('does not delete a branch that moved after PR verification', async () => {
    const replies = normal();
    replies[3].body = { ref: `refs/heads/${scope.headRef}`, object: { type: 'commit', sha: 'b'.repeat(40) } };
    const { github, calls } = sequence(replies);
    await expect(verifyOwnedDraftCleanup(github, scope)).rejects.toThrow('LIVE_CLEANUP_BRANCH_REVISION_CHANGED');
    expect(calls.some(call => call.startsWith('DELETE'))).toBe(false);
  });
  it.each(['fork', 'foreign-marker', 'merged', 'non-draft'])('does not mutate an unowned or unsafe PR: %s', async kind => {
    const pr = pull();
    if (kind === 'fork') pr.head.repo = { id: 99, full_name: 'Other/fork' };
    if (kind === 'foreign-marker') pr.title = '[live-vnext:456:p1]';
    if (kind === 'merged') Object.assign(pr, { merged_at: '2026-09-09T00:00:00Z' });
    if (kind === 'non-draft') pr.draft = false;
    const { github, calls } = sequence([{ status: 200, body: pr }]);
    await expect(verifyOwnedDraftCleanup(github, scope)).rejects.toThrow('LIVE_CLEANUP_OWNERSHIP_UNVERIFIED');
    expect(calls).toHaveLength(1);
  });
  it('allows an already-absent branch only after closed owned-PR readback', async () => {
    const { github, calls } = sequence([{ status: 200, body: pull('closed') }, { status: 200, body: pull('closed') }, { status: 404, body: null }]);
    await expect(verifyOwnedDraftCleanup(github, scope)).resolves.toMatchObject({ branchDeleted: true });
    expect(calls.every(call => call.startsWith('GET'))).toBe(true);
  });
  it('imports the tested helper in the actual live E2E path', () => {
    const source = readFileSync('tests/e2e/five-draft-pr-paths.spec.ts', 'utf8');
    expect(source).toContain("from './helpers/live-draft-cleanup'");
    expect(source).toContain('return verifyOwnedDraftCleanup(');
    expect(source).not.toContain('deleted.status === 422');
  });
});
