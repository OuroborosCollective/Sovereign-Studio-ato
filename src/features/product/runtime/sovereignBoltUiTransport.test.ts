import { describe, expect, it } from 'vitest';
import { buildBoltSnapshotJob } from './sovereignBoltSnapshotExecutor';
import {
  BOLT_UI_TRANSPORT_SCHEMA,
  buildBoltGitImportUrl,
  buildBoltUiTransportPlan,
  buildGitHubRevisionArchiveUrl,
  normalizeBoltBaseUrl,
} from './sovereignBoltUiTransport';

const REVISION = '0123456789abcdef0123456789abcdef01234567';
const LIVE_BOLT = 'https://boltdiy-m3bq.srv1491137.hstgr.cloud/';

function job() {
  return buildBoltSnapshotJob({
    repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
    branch: 'main',
    revision: REVISION,
  });
}

describe('sovereignBoltUiTransport', () => {
  it('accepts only credential-free HTTPS Bolt origins', () => {
    expect(normalizeBoltBaseUrl(LIVE_BOLT)).toBe('https://boltdiy-m3bq.srv1491137.hstgr.cloud');
    expect(normalizeBoltBaseUrl('http://bolt.example')).toBeNull();
    expect(normalizeBoltBaseUrl('https://user:pass@bolt.example')).toBeNull();
    expect(normalizeBoltBaseUrl('https://bolt.example/?token=secret')).toBeNull();
  });

  it('builds an exact-revision GitHub archive URL', () => {
    expect(buildGitHubRevisionArchiveUrl('OuroborosCollective/Sovereign-Studio-ato', REVISION))
      .toBe(`https://github.com/OuroborosCollective/Sovereign-Studio-ato/archive/${REVISION}.zip`);
    expect(() => buildGitHubRevisionArchiveUrl('OuroborosCollective/Sovereign-Studio-ato', 'main'))
      .toThrow(/exact lowercase 40-character Git revision/);
  });

  it('builds the live Bolt git import route without pretending it pins a revision', () => {
    const launch = buildBoltGitImportUrl(LIVE_BOLT, 'OuroborosCollective/Sovereign-Studio-ato');
    expect(launch).toBe(
      'https://boltdiy-m3bq.srv1491137.hstgr.cloud/git?url=' +
      encodeURIComponent('https://github.com/OuroborosCollective/Sovereign-Studio-ato.git'),
    );

    const plan = buildBoltUiTransportPlan({ job: job(), boltBaseUrl: LIVE_BOLT, mode: 'git-import' });
    expect(plan.schema).toBe(BOLT_UI_TRANSPORT_SCHEMA);
    expect(plan.revisionPinnedInput).toBe(false);
    expect(plan.executionEvidenceAuthoritative).toBe(false);
    expect(plan.persistence).toBe('ephemeral-browser-workspace');
    expect(plan.blockers.join(' ')).toContain('not revision-bound');
  });

  it('treats an exact archive as pinned input but not as execution proof', () => {
    const plan = buildBoltUiTransportPlan({ job: job(), boltBaseUrl: LIVE_BOLT, mode: 'revision-archive' });

    expect(plan.revisionPinnedInput).toBe(true);
    expect(plan.launchUrl).toBeUndefined();
    expect(plan.revisionArchiveUrl).toContain(REVISION);
    expect(plan.executionEvidenceAuthoritative).toBe(false);
    expect(plan.blockers.join(' ')).toContain('No authenticated Bolt archive-upload/readback API has been verified');
  });

  it('never projects the Bolt handoff as a persistent local workspace', () => {
    const gitPlan = buildBoltUiTransportPlan({ job: job(), boltBaseUrl: LIVE_BOLT, mode: 'git-import' });
    const archivePlan = buildBoltUiTransportPlan({ job: job(), boltBaseUrl: LIVE_BOLT, mode: 'revision-archive' });

    expect(gitPlan.persistence).toBe('ephemeral-browser-workspace');
    expect(archivePlan.persistence).toBe('ephemeral-browser-workspace');
  });
});
