import { describe, expect, it } from 'vitest';
import {
  appendEvidenceEntry,
  assertEvidenceEntryValid,
  assertEvidenceLedgerValid,
  createEvidenceEntry,
  createInitialEvidenceLedger,
  filterEvidenceEntries,
  formatEvidenceEntryLine,
  getBlockedOrUnknownEntries,
  getEvidenceByCategory,
  getEvidenceByStatus,
  getEvidenceSummaryByCategory,
  getLatestEvidenceByCategory,
  summarizeEvidenceLedger,
  validateEvidenceEntry,
  validateEvidenceLedger,
  type EvidenceCategory,
  type EvidenceLedgerEntry,
  type EvidenceStatus,
} from './evidenceLedger';

describe('evidenceLedger', () => {
  describe('createEvidenceEntry', () => {
    it('creates a valid evidence entry with all fields', () => {
      const entry = createEvidenceEntry({
        category: 'workflow-watch',
        source: { type: 'github-api', detail: 'commit-status endpoint' },
        status: 'success',
        reason: 'GitHub workflow checks are green.',
        location: { runId: '12345', url: 'https://github.com/example/repo/actions/runs/12345' },
        metadata: { checkCount: 3 },
      });

      expect(entry.id).toMatch(/^ev-[a-f0-9]+$/);
      expect(entry.category).toBe('workflow-watch');
      expect(entry.source.type).toBe('github-api');
      expect(entry.source.detail).toBe('commit-status endpoint');
      expect(entry.status).toBe('success');
      expect(entry.reason).toBe('GitHub workflow checks are green.');
      expect(entry.location?.runId).toBe('12345');
      expect(entry.location?.url).toContain('github.com');
      expect(entry.metadata?.checkCount).toBe(3);
      expect(entry.timestamp).toBeGreaterThan(0);
      expect(() => assertEvidenceEntryValid(entry)).not.toThrow();
    });

    it('creates entry with minimal fields', () => {
      const entry = createEvidenceEntry({
        category: 'draft-pr',
        source: { type: 'local-runtime' },
        status: 'pending',
        reason: 'Draft PR creation in progress.',
      });

      expect(entry.id).toMatch(/^ev-[a-f0-9]+$/);
      expect(entry.category).toBe('draft-pr');
      expect(entry.source.type).toBe('local-runtime');
      expect(entry.status).toBe('pending');
      expect(entry.reason).toBe('Draft PR creation in progress.');
      expect(entry.location).toBeUndefined();
      expect(entry.metadata).toBeUndefined();
    });

    it('uses provided timestamp', () => {
      const fixedTime = 1700000000000;
      const entry = createEvidenceEntry({
        category: 'validation',
        source: { type: 'system-check' },
        status: 'success',
        reason: 'Validation passed.',
        timestamp: fixedTime,
      });

      expect(entry.timestamp).toBe(fixedTime);
    });
  });

  describe('validateEvidenceEntry', () => {
    it('rejects entry with missing id', () => {
      const entry: EvidenceLedgerEntry = {
        id: '',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: 'test',
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('id is required');
    });

    it('rejects entry with unknown category', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'unknown-category' as EvidenceCategory,
        source: { type: 'github-api' },
        status: 'success',
        reason: 'test',
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('Unknown evidence category');
    });

    it('rejects entry with unknown status', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'invalid-status' as EvidenceStatus,
        reason: 'test',
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('Unknown evidence status');
    });

    it('rejects entry with empty reason', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: '',
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('reason is required');
    });

    it('rejects entry with invalid timestamp', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: 'test',
        timestamp: -1,
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('timestamp must be a positive number');
    });

    it('rejects entry with path traversal in filePath', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'repair',
        source: { type: 'local-runtime' },
        status: 'pending',
        reason: 'Repair in progress.',
        location: { filePath: '../../../etc/passwd' },
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('invalid path traversal');
    });

    it('rejects entry with secret-like content', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: 'token=ghp_secret_token_1234567890',
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('secret-like');
    });

    it('warns about non-HTTP URL', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: 'test',
        location: { url: 'ftp://example.com/file' },
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.warnings.join(' ')).toContain('not an HTTP URL');
    });

    it('accepts entry with all valid fields', () => {
      const entry: EvidenceLedgerEntry = {
        id: 'ev-test-123',
        category: 'validation',
        source: { type: 'system-check', detail: 'functional guards' },
        status: 'success',
        reason: 'All guards passed.',
        location: { filePath: 'src/guards.ts', runId: 'run-456' },
        metadata: { guardCount: 5 },
        timestamp: Date.now(),
      };

      const report = validateEvidenceEntry(entry);
      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
    });
  });

  describe('Evidence Ledger operations', () => {
    let ledger: ReturnType<typeof createInitialEvidenceLedger>;

    beforeEach(() => {
      ledger = createInitialEvidenceLedger();
    });

    describe('appendEvidenceEntry', () => {
      it('appends entry to empty ledger', () => {
        const entry = createEvidenceEntry({
          category: 'draft-pr',
          source: { type: 'user-action' },
          status: 'success',
          reason: 'Draft PR created.',
        });

        const next = appendEvidenceEntry(ledger, entry);
        expect(next.entries).toHaveLength(1);
        expect(next.entries[0].id).toBe(entry.id);
      });

      it('limits entries to maxEntries', () => {
        for (let i = 0; i < 250; i++) {
          const entry = createEvidenceEntry({
            category: 'workflow-watch',
            source: { type: 'github-api' },
            status: 'success',
            reason: `Entry ${i}`,
            timestamp: Date.now() + i,
          });
          ledger = appendEvidenceEntry(ledger, entry, 200);
        }

        expect(ledger.entries).toHaveLength(200);
      });
    });

    describe('getEvidenceByCategory', () => {
      it('filters entries by category', () => {
        const entry1 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'success',
          reason: 'Workflow watch success.',
        });
        const entry2 = createEvidenceEntry({
          category: 'draft-pr',
          source: { type: 'user-action' },
          status: 'success',
          reason: 'Draft PR created.',
        });
        const entry3 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'failure',
          reason: 'Workflow watch failure.',
        });

        ledger = appendEvidenceEntry(ledger, entry1);
        ledger = appendEvidenceEntry(ledger, entry2);
        ledger = appendEvidenceEntry(ledger, entry3);

        const workflowEntries = getEvidenceByCategory(ledger, 'workflow-watch');
        expect(workflowEntries).toHaveLength(2);
        expect(workflowEntries[0].status).toBe('success');
        expect(workflowEntries[1].status).toBe('failure');

        const prEntries = getEvidenceByCategory(ledger, 'draft-pr');
        expect(prEntries).toHaveLength(1);
      });
    });

    describe('getLatestEvidenceByCategory', () => {
      it('returns most recent entry for category', () => {
        const entry1 = createEvidenceEntry({
          category: 'repair',
          source: { type: 'local-runtime' },
          status: 'pending',
          reason: 'First repair entry.',
          timestamp: 1000,
        });
        const entry2 = createEvidenceEntry({
          category: 'repair',
          source: { type: 'local-runtime' },
          status: 'success',
          reason: 'Second repair entry.',
          timestamp: 2000,
        });

        ledger = appendEvidenceEntry(ledger, entry1);
        ledger = appendEvidenceEntry(ledger, entry2);

        const latest = getLatestEvidenceByCategory(ledger, 'repair');
        expect(latest?.status).toBe('success');
        expect(latest?.reason).toBe('Second repair entry.');
      });

      it('returns undefined for missing category', () => {
        const latest = getLatestEvidenceByCategory(ledger, 'validation');
        expect(latest).toBeUndefined();
      });
    });

    describe('getEvidenceByStatus', () => {
      it('filters entries by status', () => {
        const entry1 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'success',
          reason: 'Success entry.',
        });
        const entry2 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'blocked',
          reason: 'Blocked entry.',
        });
        const entry3 = createEvidenceEntry({
          category: 'validation',
          source: { type: 'system-check' },
          status: 'blocked',
          reason: 'Another blocked entry.',
        });

        ledger = appendEvidenceEntry(ledger, entry1);
        ledger = appendEvidenceEntry(ledger, entry2);
        ledger = appendEvidenceEntry(ledger, entry3);

        const blocked = getEvidenceByStatus(ledger, 'blocked');
        expect(blocked).toHaveLength(2);
      });
    });

    describe('getBlockedOrUnknownEntries', () => {
      it('returns only blocked or unknown entries', () => {
        const entry1 = createEvidenceEntry({
          category: 'runtime-status',
          source: { type: 'system-check' },
          status: 'success',
          reason: 'Success.',
        });
        const entry2 = createEvidenceEntry({
          category: 'runtime-status',
          source: { type: 'system-check' },
          status: 'blocked',
          reason: 'Blocked.',
        });
        const entry3 = createEvidenceEntry({
          category: 'runtime-status',
          source: { type: 'system-check' },
          status: 'unknown',
          reason: 'Unknown.',
        });

        ledger = appendEvidenceEntry(ledger, entry1);
        ledger = appendEvidenceEntry(ledger, entry2);
        ledger = appendEvidenceEntry(ledger, entry3);

        const unclear = getBlockedOrUnknownEntries(ledger);
        expect(unclear).toHaveLength(2);
        expect(unclear.map((e) => e.status)).toContain('blocked');
        expect(unclear.map((e) => e.status)).toContain('unknown');
      });
    });

    describe('summarizeEvidenceLedger', () => {
      it('summarizes ledger contents', () => {
        const entry1 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'success',
          reason: 'Success.',
        });
        const entry2 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'blocked',
          reason: 'Blocked.',
        });

        ledger = appendEvidenceEntry(ledger, entry1);
        ledger = appendEvidenceEntry(ledger, entry2);

        const summary = summarizeEvidenceLedger(ledger);
        expect(summary).toContain('2 evidence entries');
        expect(summary).toContain('workflow-watch');
        expect(summary).toContain('success');
        expect(summary).toContain('blocked');
        expect(summary).toContain('Blocked/unknown: 1');
      });

      it('handles empty ledger', () => {
        const summary = summarizeEvidenceLedger(ledger);
        expect(summary).toBe('Evidence ledger is empty.');
      });
    });

    describe('formatEvidenceEntryLine', () => {
      it('formats entry with location', () => {
        const entry = createEvidenceEntry({
          category: 'draft-pr',
          source: { type: 'user-action' },
          status: 'success',
          reason: 'Draft PR created.',
          location: { filePath: 'src/pr.ts', runId: 'run-123' },
          timestamp: 1700000000000,
        });

        const line = formatEvidenceEntryLine(entry);
        expect(line).toContain('[draft-pr]');
        expect(line).toContain('[success]');
        expect(line).toContain('[user-action]');
        expect(line).toContain('Draft PR created.');
        expect(line).toContain('src/pr.ts');
        expect(line).toContain('run-123');
      });

      it('formats entry without location', () => {
        const entry = createEvidenceEntry({
          category: 'validation',
          source: { type: 'system-check' },
          status: 'success',
          reason: 'All checks passed.',
          timestamp: 1700000000000,
        });

        const line = formatEvidenceEntryLine(entry);
        expect(line).toContain('[validation]');
        expect(line).toContain('[system-check]');
        expect(line).toContain('All checks passed.');
      });
    });

    describe('filterEvidenceEntries', () => {
      it('filters with custom predicate', () => {
        const entry1 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'success',
          reason: 'Success entry.',
        });
        const entry2 = createEvidenceEntry({
          category: 'workflow-watch',
          source: { type: 'github-api' },
          status: 'failure',
          reason: 'Failure entry.',
        });

        ledger = appendEvidenceEntry(ledger, entry1);
        ledger = appendEvidenceEntry(ledger, entry2);

        const failures = filterEvidenceEntries(ledger, (e) => e.status === 'failure');
        expect(failures).toHaveLength(1);
        expect(failures[0].reason).toBe('Failure entry.');
      });
    });

    describe('getEvidenceSummaryByCategory', () => {
      it('counts entries by category and status', () => {
        const categories: EvidenceCategory[] = ['draft-pr', 'workflow-watch', 'repair', 'runtime-status', 'validation'];
        const statuses: EvidenceStatus[] = ['success', 'failure', 'unknown', 'blocked', 'pending'];

        for (const cat of categories) {
          for (const status of statuses) {
            const entry = createEvidenceEntry({
              category: cat,
              source: { type: 'local-runtime' },
              status,
              reason: `${cat} - ${status}`,
            });
            ledger = appendEvidenceEntry(ledger, entry);
          }
        }

        const summary = getEvidenceSummaryByCategory(ledger);

        for (const cat of categories) {
          expect(summary[cat].total).toBe(5);
          expect(summary[cat].success).toBe(1);
          expect(summary[cat].failure).toBe(1);
          expect(summary[cat].unknown).toBe(1);
          expect(summary[cat].blocked).toBe(1);
          expect(summary[cat].pending).toBe(1);
        }
      });
    });
  });

  describe('validateEvidenceLedger', () => {
    it('rejects ledger with non-array entries', () => {
      const ledger = { entries: 'not-an-array' as unknown as [] };
      const report = validateEvidenceLedger(ledger);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('must be an array');
    });

    it('detects duplicate entry ids', () => {
      const entry = createEvidenceEntry({
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: 'Duplicate id test.',
      });

      const ledger = {
        entries: [
          { ...entry },
          { ...entry, id: entry.id }, // Duplicate id
        ],
      };

      const report = validateEvidenceLedger(ledger);
      expect(report.valid).toBe(true); // Still valid, just warnings
      expect(report.warnings.join(' ')).toContain('Duplicate');
    });
  });

  describe('assertEvidenceEntryValid', () => {
    it('throws on invalid entry', () => {
      const entry: EvidenceLedgerEntry = {
        id: '',
        category: 'workflow-watch',
        source: { type: 'github-api' },
        status: 'success',
        reason: 'test',
        timestamp: Date.now(),
      };

      expect(() => assertEvidenceEntryValid(entry)).toThrow('Evidence entry is invalid');
    });
  });

  describe('assertEvidenceLedgerValid', () => {
    it('throws on invalid ledger', () => {
      const ledger = { entries: 'not-an-array' as unknown as [] };
      expect(() => assertEvidenceLedgerValid(ledger)).toThrow('Evidence ledger entries must be an array');
    });
  });
});