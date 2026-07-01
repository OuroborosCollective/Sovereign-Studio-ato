import { describe, it, expect } from 'vitest';
import {
  createPatternMemoryStore,
  addPatternEntry,
  recordPatternReuse,
  verifyPatternEntry,
  queryPatternEntries,
  eraseUserPatterns,
  derivePatternMemoryCounters,
  buildPatternMemorySummaryText,
  validatePatternMemoryIntake,
  buildLearnedPatternEntry,
  validatePatternMemoryStore,
  type PatternMemoryIntake,
} from './patternMemoryRuntime';

const BASE_INTAKE: PatternMemoryIntake = {
  ownerScope: 'local-user',
  sourceTraceId: 'trace-001',
  title: 'TypeScript import fix',
  summary: 'Removes unused imports from TypeScript files.',
  tags: ['typescript', 'imports', 'cleanup'],
  verified: false,
  localExecutable: false,
  now: 1000,
};

describe('patternMemoryRuntime', () => {
  describe('createPatternMemoryStore', () => {
    it('creates an empty store with version 1', () => {
      const store = createPatternMemoryStore(1000);
      expect(store.version).toBe(1);
      expect(store.entries).toHaveLength(0);
      expect(store.updatedAt).toBe(1000);
    });
  });

  describe('validatePatternMemoryIntake', () => {
    it('passes for valid intake', () => {
      const report = validatePatternMemoryIntake(BASE_INTAKE);
      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
    });

    it('rejects unknown ownerScope', () => {
      const report = validatePatternMemoryIntake({ ...BASE_INTAKE, ownerScope: 'unknown' as never });
      expect(report.valid).toBe(false);
      expect(report.errors.some((e) => e.includes('ownerScope'))).toBe(true);
    });

    it('rejects empty title', () => {
      const report = validatePatternMemoryIntake({ ...BASE_INTAKE, title: '' });
      expect(report.valid).toBe(false);
      expect(report.errors.some((e) => e.includes('title'))).toBe(true);
    });

    it('rejects empty summary', () => {
      const report = validatePatternMemoryIntake({ ...BASE_INTAKE, summary: '' });
      expect(report.valid).toBe(false);
      expect(report.errors.some((e) => e.includes('summary'))).toBe(true);
    });

    it('rejects intake with sensitive-looking content', () => {
      const report = validatePatternMemoryIntake({ ...BASE_INTAKE, summary: 'token=ghp_abc12345678' });
      expect(report.valid).toBe(false);
      expect(report.errors.some((e) => e.includes('sensitive'))).toBe(true);
    });

    it('warns when localExecutable=true but verified=false', () => {
      const report = validatePatternMemoryIntake({ ...BASE_INTAKE, localExecutable: true, verified: false });
      expect(report.warnings.some((w) => w.includes('localExecutable'))).toBe(true);
    });
  });

  describe('buildLearnedPatternEntry', () => {
    it('builds entry with correct defaults', () => {
      const entry = buildLearnedPatternEntry(BASE_INTAKE);
      expect(entry.id).toMatch(/^pat-/);
      expect(entry.ownerScope).toBe('local-user');
      expect(entry.title).toBe('TypeScript import fix');
      expect(entry.verified).toBe(false);
      expect(entry.localExecutable).toBe(false);
      expect(entry.reuseCount).toBe(0);
      expect(entry.lastUsedAt).toBeNull();
      expect(entry.createdAt).toBe(1000);
    });

    it('forces localExecutable=false when verified=false', () => {
      const entry = buildLearnedPatternEntry({ ...BASE_INTAKE, localExecutable: true, verified: false });
      expect(entry.localExecutable).toBe(false);
    });

    it('allows localExecutable=true when verified=true', () => {
      const entry = buildLearnedPatternEntry({ ...BASE_INTAKE, localExecutable: true, verified: true });
      expect(entry.localExecutable).toBe(true);
    });

    it('redacts sensitive content in title/summary', () => {
      const entry = buildLearnedPatternEntry({ ...BASE_INTAKE, summary: 'use token=abc123456789xyz here' });
      expect(entry.summary).toContain('<redacted>');
    });

    it('produces stable id for same input', () => {
      const a = buildLearnedPatternEntry(BASE_INTAKE);
      const b = buildLearnedPatternEntry(BASE_INTAKE);
      expect(a.id).toBe(b.id);
    });
  });

  describe('addPatternEntry', () => {
    it('adds a new entry to an empty store', () => {
      const store = createPatternMemoryStore(1000);
      const next = addPatternEntry(store, BASE_INTAKE);
      expect(next.entries).toHaveLength(1);
      expect(next.entries[0].title).toBe('TypeScript import fix');
    });

    it('increments reuseCount on duplicate entry', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, now: 2000 });
      expect(s2.entries).toHaveLength(1);
      expect(s2.entries[0].reuseCount).toBe(1);
      expect(s2.entries[0].lastUsedAt).toBe(2000);
    });

    it('throws on invalid intake', () => {
      const store = createPatternMemoryStore(1000);
      expect(() => addPatternEntry(store, { ...BASE_INTAKE, title: '' })).toThrow();
    });
  });

  describe('recordPatternReuse', () => {
    it('increments reuseCount and sets lastUsedAt', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const entryId = s1.entries[0].id;
      const s2 = recordPatternReuse(s1, entryId, 5000);
      expect(s2.entries[0].reuseCount).toBe(1);
      expect(s2.entries[0].lastUsedAt).toBe(5000);
    });

    it('does not affect other entries', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, title: 'Different pattern', sourceTraceId: 'trace-002' });
      const entryId = s2.entries.find((e) => e.title === 'TypeScript import fix')!.id;
      const s3 = recordPatternReuse(s2, entryId, 5000);
      expect(s3.entries.find((e) => e.title === 'Different pattern')!.reuseCount).toBe(0);
    });
  });

  describe('verifyPatternEntry', () => {
    it('marks an entry as verified', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const entryId = s1.entries[0].id;
      const s2 = verifyPatternEntry(s1, entryId, false, 2000);
      expect(s2.entries[0].verified).toBe(true);
      expect(s2.entries[0].localExecutable).toBe(false);
    });

    it('allows localExecutable=true when verifying', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const entryId = s1.entries[0].id;
      const s2 = verifyPatternEntry(s1, entryId, true, 2000);
      expect(s2.entries[0].verified).toBe(true);
      expect(s2.entries[0].localExecutable).toBe(true);
    });
  });

  describe('queryPatternEntries', () => {
    it('returns all entries when no filter', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, title: 'Another pattern', sourceTraceId: 'trace-002' });
      const results = queryPatternEntries(s2);
      expect(results).toHaveLength(2);
    });

    it('filters by ownerScope', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, ownerScope: 'shared-derived', title: 'Shared', sourceTraceId: 'trace-002' });
      const results = queryPatternEntries(s2, { ownerScope: 'local-user' });
      expect(results).toHaveLength(1);
      expect(results[0].ownerScope).toBe('local-user');
    });

    it('filters by verified', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const entryId = s1.entries[0].id;
      const s2 = verifyPatternEntry(s1, entryId, false, 2000);
      const s3 = addPatternEntry(s2, { ...BASE_INTAKE, title: 'Unverified', sourceTraceId: 'trace-002' });
      const verified = queryPatternEntries(s3, { verified: true });
      expect(verified).toHaveLength(1);
      expect(verified[0].verified).toBe(true);
    });

    it('filters by tag', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, tags: ['css'], title: 'CSS pattern', sourceTraceId: 'trace-002' });
      const results = queryPatternEntries(s2, { tag: 'typescript' });
      expect(results).toHaveLength(1);
      expect(results[0].tags).toContain('typescript');
    });
  });

  describe('eraseUserPatterns', () => {
    it('removes local-user and remote-user entries', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, ownerScope: 'remote-user', title: 'Remote', sourceTraceId: 'trace-002' });
      const s3 = addPatternEntry(s2, { ...BASE_INTAKE, ownerScope: 'shared-derived', title: 'Shared', sourceTraceId: 'trace-003' });
      const { store: erased, result } = eraseUserPatterns(s3, 5000);
      expect(erased.entries).toHaveLength(1);
      expect(erased.entries[0].ownerScope).toBe('shared-derived');
      expect(result.erasedCount).toBe(2);
      expect(result.remainingCount).toBe(1);
    });

    it('retains shared-derived entries after erasure', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, { ...BASE_INTAKE, ownerScope: 'shared-derived', title: 'Shared', sourceTraceId: 'trace-001' });
      const { store: erased } = eraseUserPatterns(s1, 5000);
      expect(erased.entries).toHaveLength(1);
    });

    it('returns empty store when all entries are user-scoped', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const { store: erased, result } = eraseUserPatterns(s1, 5000);
      expect(erased.entries).toHaveLength(0);
      expect(result.erasedCount).toBe(1);
      expect(result.remainingCount).toBe(0);
    });
  });

  describe('derivePatternMemoryCounters', () => {
    it('returns zero counters for empty store', () => {
      const store = createPatternMemoryStore(1000);
      const counters = derivePatternMemoryCounters(store);
      expect(counters.totalStored).toBe(0);
      expect(counters.verifiedCount).toBe(0);
      expect(counters.localExecutableCount).toBe(0);
      expect(counters.frequentlyUsedCount).toBe(0);
      expect(counters.lastSuccessfulReuseAt).toBeNull();
    });

    it('counts verified and local-executable entries', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, title: 'Verified+local', sourceTraceId: 'trace-002', verified: true, localExecutable: true });
      const counters = derivePatternMemoryCounters(s2);
      expect(counters.totalStored).toBe(2);
      expect(counters.verifiedCount).toBe(1);
      expect(counters.localExecutableCount).toBe(1);
    });

    it('tracks last successful reuse timestamp', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const entryId = s1.entries[0].id;
      const s2 = recordPatternReuse(s1, entryId, 9999);
      const counters = derivePatternMemoryCounters(s2);
      expect(counters.lastSuccessfulReuseAt).toBe(9999);
    });

    it('counts entries by scope', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const s2 = addPatternEntry(s1, { ...BASE_INTAKE, ownerScope: 'shared-derived', title: 'Shared', sourceTraceId: 'trace-002' });
      const counters = derivePatternMemoryCounters(s2);
      expect(counters.localUserCount).toBe(1);
      expect(counters.sharedDerivedCount).toBe(1);
    });
  });

  describe('buildPatternMemorySummaryText', () => {
    it('builds non-empty summary text', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const counters = derivePatternMemoryCounters(s1);
      const text = buildPatternMemorySummaryText(counters);
      expect(text).toContain('gespeicherte Pattern');
    });
  });

  describe('validatePatternMemoryStore', () => {
    it('validates a valid store', () => {
      const store = createPatternMemoryStore(1000);
      const s1 = addPatternEntry(store, BASE_INTAKE);
      const report = validatePatternMemoryStore(s1);
      expect(report.valid).toBe(true);
    });
  });
});
