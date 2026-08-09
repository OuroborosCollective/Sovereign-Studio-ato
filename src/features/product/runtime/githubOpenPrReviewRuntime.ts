import { resolvePrimaryBridgeConfig } from '../llm/primaryBridgeConfig';
import type { DevChatRepoSnapshot } from './devChatWorkerBridge';

const BACKEND_BASE = resolvePrimaryBridgeConfig().backendBaseUrl;
export const OPEN_PR_REVIEW_ENDPOINT = `${BACKEND_BASE}/api/toolchain/github/open-pr-review` as const;

export interface OpenPrCheckSummary {
  readonly successful: number;
  readonly pending: number;
  readonly failed: number;
  readonly failedNames: readonly string[];
  readonly pendingNames: readonly string[];
}

export interface OpenPrReviewItem {
  readonly number: number;
  readonly title: string;
  readonly url: string;
  readonly draft: boolean;
  readonly headSha: string;
  readonly baseRef: string;
  readonly mergeable: boolean | null;
  readonly mergeableState: string;
  readonly changedFiles: number;
  readonly additions: number;
  readonly deletions: number;
  readonly filePaths: readonly string[];
  readonly generatedArtifactCandidates: readonly string[];
  readonly checkSummary: OpenPrCheckSummary;
  readonly blockers: readonly string[];
}

export interface OpenPrReviewEvidence {
  readonly ok: boolean;
  readonly owner: string;
  readonly repo: string;
  readonly openPrCount: number;
  readonly pullRequests: readonly OpenPrReviewItem[];
  readonly reviewMode: 'read_only';
  readonly githubWriteRequired: false;
  readonly executorStarted: false;
  readonly bounded: true;
}

export interface OpenPrReviewResult {
  readonly ok: boolean;
  readonly evidence?: OpenPrReviewEvidence;
  readonly error?: string;
  readonly status?: number;
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string').slice(0, 100)
    : [];
}

function parseEvidence(payload: unknown): OpenPrReviewEvidence | null {
  if (!payload || typeof payload !== 'object') return null;
  const root = payload as Record<string, unknown>;
  if (root.ok !== true || root.reviewMode !== 'read_only' || root.githubWriteRequired !== false || root.executorStarted !== false) {
    return null;
  }
  const owner = typeof root.owner === 'string' ? root.owner : '';
  const repo = typeof root.repo === 'string' ? root.repo : '';
  const rawPrs = Array.isArray(root.pullRequests) ? root.pullRequests : [];
  const pullRequests: OpenPrReviewItem[] = rawPrs.slice(0, 20).flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const pr = item as Record<string, unknown>;
    const number = Number(pr.number);
    if (!Number.isInteger(number) || number <= 0) return [];
    const rawSummary = pr.checkSummary && typeof pr.checkSummary === 'object'
      ? pr.checkSummary as Record<string, unknown>
      : {};
    return [{
      number,
      title: typeof pr.title === 'string' ? pr.title : '',
      url: typeof pr.url === 'string' ? pr.url : '',
      draft: pr.draft === true,
      headSha: typeof pr.headSha === 'string' ? pr.headSha : '',
      baseRef: typeof pr.baseRef === 'string' ? pr.baseRef : '',
      mergeable: typeof pr.mergeable === 'boolean' ? pr.mergeable : null,
      mergeableState: typeof pr.mergeableState === 'string' ? pr.mergeableState : 'unknown',
      changedFiles: Math.max(0, Number(pr.changedFiles) || 0),
      additions: Math.max(0, Number(pr.additions) || 0),
      deletions: Math.max(0, Number(pr.deletions) || 0),
      filePaths: asStringList(pr.filePaths),
      generatedArtifactCandidates: asStringList(pr.generatedArtifactCandidates).slice(0, 20),
      checkSummary: {
        successful: Math.max(0, Number(rawSummary.successful) || 0),
        pending: Math.max(0, Number(rawSummary.pending) || 0),
        failed: Math.max(0, Number(rawSummary.failed) || 0),
        failedNames: asStringList(rawSummary.failedNames).slice(0, 20),
        pendingNames: asStringList(rawSummary.pendingNames).slice(0, 20),
      },
      blockers: asStringList(pr.blockers).slice(0, 20),
    }];
  });
  return {
    ok: true,
    owner,
    repo,
    openPrCount: pullRequests.length,
    pullRequests,
    reviewMode: 'read_only',
    githubWriteRequired: false,
    executorStarted: false,
    bounded: true,
  };
}

export async function fetchOpenPrReviewEvidence(
  snapshot: DevChatRepoSnapshot,
  fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
): Promise<OpenPrReviewResult> {
  try {
    const response = await fetchImpl(OPEN_PR_REVIEW_ENDPOINT, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ owner: snapshot.owner, repo: snapshot.repo, limit: 20 }),
    });
    const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: typeof payload.error === 'string'
          ? payload.error
          : `PR-Review HTTP ${response.status}`,
      };
    }
    const evidence = parseEvidence(payload);
    if (!evidence) {
      return { ok: false, status: response.status, error: 'PR-Review lieferte kein gültiges read-only Evidence-Schema.' };
    }
    return { ok: true, status: response.status, evidence };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'PR-Review konnte nicht geladen werden.',
    };
  }
}

function shortSha(value: string): string {
  return value.length >= 12 ? value.slice(0, 12) : value || 'unbekannt';
}

export function formatOpenPrReviewEvidence(evidence: OpenPrReviewEvidence): string {
  if (evidence.pullRequests.length === 0) {
    return [
      `Offene PRs: 0 · ${evidence.owner}/${evidence.repo}`,
      'Read-only GitHub-Evidence ist vollständig. Kein GitHub-Schreibzugang und kein Executor wurden verwendet.',
    ].join('\n');
  }

  const lines = [
    `Offene PRs: ${evidence.pullRequests.length} · ${evidence.owner}/${evidence.repo}`,
    'Quelle: serverseitige GitHub-API-Read-Evidence · kein GitHub-Schreibzugang · kein Executor.',
    '',
  ];

  for (const pr of evidence.pullRequests) {
    const mergeability = pr.mergeable === true
      ? `mergeable (${pr.mergeableState})`
      : pr.mergeable === false
        ? `nicht mergeable (${pr.mergeableState})`
        : `Mergebarkeit noch unbekannt (${pr.mergeableState})`;
    lines.push(`#${pr.number} ${pr.draft ? '[Draft] ' : ''}${pr.title}`);
    lines.push(`Scope: ${pr.changedFiles} Dateien · +${pr.additions}/-${pr.deletions} · Head ${shortSha(pr.headSha)} → ${pr.baseRef || 'main'}`);
    lines.push(`Mergebarkeit: ${mergeability}`);
    lines.push(`Checks: ${pr.checkSummary.successful} grün/neutral · ${pr.checkSummary.pending} offen · ${pr.checkSummary.failed} fehlgeschlagen`);
    if (pr.checkSummary.failedNames.length > 0) {
      lines.push(`Fehlgeschlagene Checks: ${pr.checkSummary.failedNames.join(', ')}`);
    }
    if (pr.checkSummary.pendingNames.length > 0) {
      lines.push(`Offene Checks: ${pr.checkSummary.pendingNames.join(', ')}`);
    }
    if (pr.generatedArtifactCandidates.length > 0) {
      lines.push(`Generierte-Artefakt-Kandidaten: ${pr.generatedArtifactCandidates.join(', ')}`);
    } else {
      lines.push('Generierte-Artefakt-Kandidaten: keine in den ersten 100 geänderten Dateien erkannt.');
    }
    lines.push(`Blocker: ${pr.blockers.length > 0 ? pr.blockers.join(', ') : 'keine aus der gelesenen Merge-/Check-Evidence'}`);
    lines.push('');
  }
  return lines.join('\n').trimEnd();
}
