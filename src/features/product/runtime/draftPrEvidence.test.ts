import { describe, expect, it } from 'vitest';
import {
  createDraftPrPreparationEvidence,
  createDraftPrCreationEvidence,
  appendDraftPrPreparationEvidence,
  appendDraftPrCreationEvidence,
  getLatestDraftPrEvidence,
  isLatestDraftPrSuccessful,
} from './draftPrEvidence';
import { createInitialEvidenceLedger, appendEvidenceEntry } from './evidenceLedger';

describe('Draft PR Evidence Integration', () => {
  describe('createDraftPrPreparationEvidence', () => {
    it('creates evidence entry with success status when allowed', () => {
      const evidence = createDraftPrPreparationEvidence({
        jobId: 'job-123',
        decision: 'allowed',
        canCreate: true,
        headBranch: 'feature/test-branch',
        baseBranch: 'main',
      });

      expect(evidence.category).toBe('draft-pr');
      expect(evidence.status).toBe('success');
      expect(evidence.source.type).toBe('local-runtime');
      expect(evidence.source.detail).toBe('sovereign-agent-client.prepareDraftPr');
      expect(evidence.reason).toContain('allowed');
      expect(evidence.location?.branch).toBe('feature/test-branch');
      expect(evidence.metadata?.jobId).toBe('job-123');
      expect(evidence.metadata?.decision).toBe('allowed');
    });

    it('creates evidence entry with blocked status when blocked', () => {
      const evidence = createDraftPrPreparationEvidence({
        jobId: 'job-456',
        decision: 'blocked',
        canCreate: false,
        blockers: ['Missing approval', 'CI not passing'],
      });

      expect(evidence.category).toBe('draft-pr');
      expect(evidence.status).toBe('blocked');
      expect(evidence.reason).toContain('blocked');
      expect(evidence.reason).toContain('Missing approval');
    });

    it('creates evidence entry with pending status when pending', () => {
      const evidence = createDraftPrPreparationEvidence({
        jobId: 'job-789',
        decision: 'pending',
        canCreate: false,
      });

      expect(evidence.category).toBe('draft-pr');
      expect(evidence.status).toBe('pending');
      expect(evidence.reason).toContain('pending');
    });

    it('creates evidence entry with blocked status when allowed but cannot create', () => {
      const evidence = createDraftPrPreparationEvidence({
        jobId: 'job-abc',
        decision: 'allowed',
        canCreate: false,
        blockers: ['Repository not found'],
      });

      expect(evidence.status).toBe('blocked');
      expect(evidence.reason).toContain('cannot create');
    });
  });

  describe('createDraftPrCreationEvidence', () => {
    it('creates evidence entry with success status when PR created', () => {
      const evidence = createDraftPrCreationEvidence({
        jobId: 'job-123',
        status: 'created',
        prUrl: 'https://github.com/owner/repo/pull/42',
        prNumber: 42,
        headSha: 'abc123def456',
        publishedHeadSha: 'abc123def456',
        readbackHeadSha: 'abc123def456',
        branch: 'feature/test',
        ciState: 'pending',
        checkRunCount: 3,
        checksSuccessCount: 1,
        checksFailureCount: 0,
        checksPendingCount: 2,
      });

      expect(evidence.category).toBe('draft-pr');
      expect(evidence.status).toBe('success');
      expect(evidence.source.type).toBe('github-api');
      expect(evidence.source.detail).toBe('sovereign-agent-client.createDraftPr');
      expect(evidence.location?.url).toBe('https://github.com/owner/repo/pull/42');
      expect(evidence.location?.branch).toBe('feature/test');
      expect(evidence.location?.commitSha).toBe('abc123def456');
      expect(evidence.metadata?.prNumber).toBe(42);
      expect(evidence.metadata?.shaMatch).toBe(true);
    });

    it('creates evidence entry with failure status when creation failed', () => {
      const evidence = createDraftPrCreationEvidence({
        jobId: 'job-456',
        status: 'failed',
      });

      expect(evidence.category).toBe('draft-pr');
      expect(evidence.status).toBe('failure');
      expect(evidence.reason).toContain('failed');
    });

    it('creates evidence entry with failure status when verification failed', () => {
      const evidence = createDraftPrCreationEvidence({
        jobId: 'job-789',
        status: 'verification-failed',
        prUrl: 'https://github.com/owner/repo/pull/99',
        headSha: 'aaaa',
        publishedHeadSha: 'bbbb', // Mismatch!
        readbackHeadSha: 'aaaa',
      });

      expect(evidence.status).toBe('failure');
      expect(evidence.reason).toContain('verification');
      expect(evidence.metadata?.shaMatch).toBe(false);
    });

    it('handles missing optional fields gracefully', () => {
      const evidence = createDraftPrCreationEvidence({
        jobId: 'job-minimal',
        status: 'created',
      });

      expect(evidence.status).toBe('success');
      expect(evidence.metadata?.prNumber).toBeNull();
      expect(evidence.metadata?.headSha).toBeNull();
    });
  });

  describe('appendDraftPrPreparationEvidence', () => {
    it('appends preparation evidence to empty ledger', () => {
      const ledger = createInitialEvidenceLedger();
      const updated = appendDraftPrPreparationEvidence(ledger, {
        jobId: 'job-test',
        decision: 'allowed',
        canCreate: true,
      });

      expect(updated.entries).toHaveLength(1);
      expect(updated.entries[0].category).toBe('draft-pr');
    });

    it('appends multiple entries preserving order', () => {
      let ledger = createInitialEvidenceLedger();
      ledger = appendDraftPrPreparationEvidence(ledger, {
        jobId: 'job-1',
        decision: 'blocked',
        canCreate: false,
      });
      ledger = appendDraftPrCreationEvidence(ledger, {
        jobId: 'job-2',
        status: 'created',
        prUrl: 'https://github.com/test/pull/1',
        prNumber: 1,
      });

      expect(ledger.entries).toHaveLength(2);
      expect(ledger.entries[0].metadata?.jobId).toBe('job-1');
      expect(ledger.entries[1].metadata?.jobId).toBe('job-2');
    });
  });

  describe('getLatestDraftPrEvidence', () => {
    it('returns undefined for empty ledger', () => {
      const ledger = createInitialEvidenceLedger();
      expect(getLatestDraftPrEvidence(ledger)).toBeUndefined();
    });

    it('returns most recent entry by timestamp', () => {
      let ledger = createInitialEvidenceLedger();

      // Create first entry with older timestamp
      const oldEntry = createDraftPrCreationEvidence({
        jobId: 'job-old',
        status: 'created',
        prUrl: 'https://github.com/test/pull/1',
      });
      // Set explicit older timestamp
      const oldTimestamp = Date.now() - 10000;
      ledger = { entries: [{ ...oldEntry, timestamp: oldTimestamp }] };

      // Create second entry with newer timestamp
      const newEntry = createDraftPrCreationEvidence({
        jobId: 'job-new',
        status: 'created',
        prUrl: 'https://github.com/test/pull/2',
      });
      ledger = appendEvidenceEntry(ledger, newEntry);

      const latest = getLatestDraftPrEvidence(ledger);
      expect(latest?.metadata?.jobId).toBe('job-new');
    });
  });

  describe('isLatestDraftPrSuccessful', () => {
    it('returns false for empty ledger', () => {
      const ledger = createInitialEvidenceLedger();
      expect(isLatestDraftPrSuccessful(ledger)).toBe(false);
    });

    it('returns true when latest entry has success status', () => {
      let ledger = createInitialEvidenceLedger();
      ledger = appendDraftPrCreationEvidence(ledger, {
        jobId: 'job-success',
        status: 'created',
        prUrl: 'https://github.com/test/pull/1',
      });

      expect(isLatestDraftPrSuccessful(ledger)).toBe(true);
    });

    it('returns false when latest entry has failure status', () => {
      let ledger = createInitialEvidenceLedger();
      ledger = appendDraftPrCreationEvidence(ledger, {
        jobId: 'job-fail',
        status: 'failed',
      });

      expect(isLatestDraftPrSuccessful(ledger)).toBe(false);
    });

    it('returns false when latest entry has blocked status', () => {
      let ledger = createInitialEvidenceLedger();
      ledger = appendDraftPrPreparationEvidence(ledger, {
        jobId: 'job-blocked',
        decision: 'blocked',
        canCreate: false,
      });

      expect(isLatestDraftPrSuccessful(ledger)).toBe(false);
    });
  });
});
