/**
 * Bolt.diy UI transport planning.
 *
 * The observed self-hosted Bolt surface exposes browser/UI import, not an
 * authenticated execution API. This module therefore produces a deterministic
 * handoff plan and never upgrades a browser import into execution evidence.
 */

import type { BoltSnapshotJob } from './sovereignBoltSnapshotExecutor';

export const BOLT_UI_TRANSPORT_SCHEMA = 'sovereign.bolt-ui-transport.v1' as const;

export type BoltUiTransportMode = 'git-import' | 'revision-archive';

export interface BoltUiTransportPlan {
  readonly schema: typeof BOLT_UI_TRANSPORT_SCHEMA;
  readonly mode: BoltUiTransportMode;
  readonly boltBaseUrl: string;
  readonly sourceRevision: string;
  readonly cloneUrl: string;
  readonly revisionArchiveUrl: string;
  readonly launchUrl?: string;
  readonly persistence: 'ephemeral-browser-workspace';
  readonly revisionPinnedInput: boolean;
  readonly executionEvidenceAuthoritative: false;
  readonly blockers: readonly string[];
  readonly warnings: readonly string[];
}

const EXACT_GIT_SHA = /^[a-f0-9]{40}$/;
const REPO_FULL_NAME = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}

export function normalizeBoltBaseUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:') return null;
    if (url.username || url.password) return null;
    if (url.search || url.hash) return null;
    const path = url.pathname.replace(/\/+$/, '');
    return `${url.origin}${path}`;
  } catch {
    return null;
  }
}

export function buildGitHubRevisionArchiveUrl(repoFullName: string, revision: string): string {
  const repo = repoFullName.trim();
  const sha = revision.trim();
  if (!REPO_FULL_NAME.test(repo)) throw new Error('Bolt transport requires repository identity in owner/name form.');
  if (!EXACT_GIT_SHA.test(sha)) throw new Error('Bolt transport archive requires an exact lowercase 40-character Git revision.');
  return `https://github.com/${repo}/archive/${sha}.zip`;
}

export function buildBoltGitImportUrl(baseUrl: string, repoFullName: string): string {
  const base = normalizeBoltBaseUrl(baseUrl);
  const repo = repoFullName.trim();
  if (!base) throw new Error('Bolt transport requires a credential-free HTTPS base URL.');
  if (!REPO_FULL_NAME.test(repo)) throw new Error('Bolt transport requires repository identity in owner/name form.');
  const cloneUrl = `https://github.com/${repo}.git`;
  return `${base}/git?url=${encodeURIComponent(cloneUrl)}`;
}

export function buildBoltUiTransportPlan(input: {
  readonly job: BoltSnapshotJob;
  readonly boltBaseUrl: string;
  readonly mode: BoltUiTransportMode;
}): BoltUiTransportPlan {
  const base = normalizeBoltBaseUrl(input.boltBaseUrl);
  if (!base) throw new Error('Bolt transport requires a credential-free HTTPS base URL.');

  const { repoFullName, revision } = input.job.source;
  if (!REPO_FULL_NAME.test(repoFullName)) throw new Error('Bolt transport requires repository identity in owner/name form.');
  if (!EXACT_GIT_SHA.test(revision)) throw new Error('Bolt transport requires an exact lowercase 40-character Git revision.');

  const cloneUrl = `https://github.com/${repoFullName}.git`;
  const revisionArchiveUrl = buildGitHubRevisionArchiveUrl(repoFullName, revision);
  const blockers: string[] = [];
  const warnings: string[] = [
    'Bolt browser imports are remote snapshots and must never be projected as a persistent local workspace.',
  ];

  if (input.mode === 'git-import') {
    blockers.push('Bolt /git import is not revision-bound and cannot satisfy authoritative snapshot provenance.');
    warnings.push('The observed Bolt git importer clones a shallow single branch; repository contents may change between launches.');
  } else {
    blockers.push('No authenticated Bolt archive-upload/readback API has been verified; an external upload receipt is required before execution evidence is accepted.');
    warnings.push('The exact GitHub revision archive is suitable as pinned input, but archive identity alone does not prove Bolt executed it.');
  }

  return {
    schema: BOLT_UI_TRANSPORT_SCHEMA,
    mode: input.mode,
    boltBaseUrl: base,
    sourceRevision: revision,
    cloneUrl,
    revisionArchiveUrl,
    launchUrl: input.mode === 'git-import' ? buildBoltGitImportUrl(base, repoFullName) : undefined,
    persistence: 'ephemeral-browser-workspace',
    revisionPinnedInput: input.mode === 'revision-archive',
    executionEvidenceAuthoritative: false,
    blockers: unique(blockers),
    warnings: unique(warnings),
  };
}
