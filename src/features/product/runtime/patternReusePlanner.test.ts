import { describe, it, expect } from 'vitest';
import {
  planPatternReuse,
  buildPatternReuseHintActions,
  buildNoPatternHintActions,
  buildPatternReuseHintViewModel,
  type PatternReuseQuery,
} from './patternReusePlanner';
import type { LearnedPatternEntry } from './patternMemoryRuntime';

function makeEntry(overrides: Partial<LearnedPatternEntry> = {}): LearnedPatternEntry {
  return {
    id: overrides.id ?? 'pat-001',
    ownerScope: overrides.ownerScope ?? 'local-user',
    sourceTraceId: overrides.sourceTraceId ?? 'trace-001',
    title: overrides.title ?? 'Fix unused imports',
    summary: overrides.summary ?? 'Removes unused TypeScript imports from source files.',
    tags: overrides.tags ?? ['typescript', 'imports'],
    vectorRef: null,
    objectRef: null,
    verified: overrides.verified ?? true,
    localExecutable: overrides.localExecutable ?? true,
    reuseCount: overrides.reuseCount ?? 0,
    lastUsedAt: overrides.lastUsedAt ?? null,
    createdAt: overrides.createdAt ?? 1000,
    ...overrides,
  };
}

describe('patternReusePlanner', () => {
  describe('planPatternReuse', () => {
    it('returns no matches for empty entries', () => {
      const result = planPatternReuse([], { intentText: 'fix typescript imports' });
      expect(result.hasMatches).toBe(false);
      expect(result.matchCount).toBe(0);
      expect(result.topMatches).toHaveLength(0);
    });

    it('matches on title token overlap', () => {
      const entries = [makeEntry({ title: 'Fix unused TypeScript imports' })];
      const result = planPatternReuse(entries, { intentText: 'remove unused imports typescript' });
      expect(result.hasMatches).toBe(true);
      expect(result.matchCount).toBeGreaterThan(0);
    });

    it('matches on tag overlap', () => {
      const entries = [makeEntry({ tags: ['css', 'cleanup'] })];
      const result = planPatternReuse(entries, { intentText: 'cleanup project', tags: ['css'] });
      expect(result.hasMatches).toBe(true);
    });

    it('returns no match for unrelated intent', () => {
      const entries = [makeEntry({ title: 'Fix imports', summary: 'TypeScript cleanup', tags: ['ts'] })];
      const result = planPatternReuse(entries, { intentText: 'deploy production server infrastructure' });
      expect(result.hasMatches).toBe(false);
    });

    it('filters by requireVerified', () => {
      const entries = [
        makeEntry({ id: 'pat-001', verified: true }),
        makeEntry({ id: 'pat-002', verified: false, title: 'Unverified Fix', sourceTraceId: 'trace-002', localExecutable: false }),
      ];
      const result = planPatternReuse(entries, { intentText: 'fix imports typescript', requireVerified: true });
      expect(result.topMatches.every((m) => m.verified)).toBe(true);
    });

    it('filters by requireLocalExecutable', () => {
      const entries = [
        makeEntry({ id: 'pat-001', localExecutable: true }),
        makeEntry({ id: 'pat-002', localExecutable: false, title: 'Remote Only Fix', sourceTraceId: 'trace-002' }),
      ];
      const result = planPatternReuse(entries, { intentText: 'fix imports typescript', requireLocalExecutable: true });
      expect(result.topMatches.every((m) => m.localExecutable)).toBe(true);
    });

    it('counts local executable matches', () => {
      const entries = [
        makeEntry({ id: 'pat-001', localExecutable: true }),
        makeEntry({ id: 'pat-002', localExecutable: false, title: 'Non-local Fix', sourceTraceId: 'trace-002' }),
      ];
      const result = planPatternReuse(entries, { intentText: 'fix imports typescript' });
      expect(result.localExecutableCount).toBe(1);
    });

    it('sets localPrepareAvailable when local-executable matches exist', () => {
      const entries = [makeEntry({ localExecutable: true })];
      const result = planPatternReuse(entries, { intentText: 'fix imports typescript' });
      expect(result.localPrepareAvailable).toBe(true);
    });

    it('sets localPrepareAvailable=false when no local-executable matches', () => {
      const entries = [makeEntry({ localExecutable: false })];
      const result = planPatternReuse(entries, { intentText: 'fix imports typescript' });
      expect(result.localPrepareAvailable).toBe(false);
    });

    it('generates chat hint with match count', () => {
      const entries = [makeEntry()];
      const result = planPatternReuse(entries, { intentText: 'fix imports typescript' });
      expect(result.chatHint).toContain('Pattern');
    });

    it('generates no-match hint when no patterns exist', () => {
      const result = planPatternReuse([], { intentText: 'fix imports' });
      expect(result.chatHint).toContain('kein geprüftes lokales Pattern');
    });

    it('respects limit parameter', () => {
      const entries = Array.from({ length: 10 }, (_, i) =>
        makeEntry({ id: `pat-${i}`, title: `Fix typescript import ${i}`, sourceTraceId: `trace-${i}` }),
      );
      const result = planPatternReuse(entries, { intentText: 'fix typescript import', limit: 3 });
      expect(result.topMatches.length).toBeLessThanOrEqual(3);
    });
  });

  describe('buildPatternReuseHintActions', () => {
    it('includes local prepare action when available', () => {
      const result = planPatternReuse([makeEntry({ localExecutable: true })], { intentText: 'fix typescript' });
      const actions = buildPatternReuseHintActions(result);
      expect(actions).toContain('Lokal vorbereiten');
      expect(actions).toContain('Mit Modellroute starten');
      expect(actions).toContain('Patterns ansehen');
    });

    it('excludes local prepare when not available', () => {
      const result = planPatternReuse([makeEntry({ localExecutable: false })], { intentText: 'fix typescript' });
      const actions = buildPatternReuseHintActions(result);
      expect(actions).not.toContain('Lokal vorbereiten');
      expect(actions).toContain('Mit Modellroute starten');
    });

    it('returns empty actions for no matches', () => {
      const result = planPatternReuse([], { intentText: 'fix typescript' });
      const actions = buildPatternReuseHintActions(result);
      expect(actions).toHaveLength(0);
    });
  });

  describe('buildNoPatternHintActions', () => {
    it('returns empty array', () => {
      expect(buildNoPatternHintActions()).toHaveLength(0);
    });
  });

  describe('buildPatternReuseHintViewModel', () => {
    it('builds a complete view model with matches', () => {
      const entries = [makeEntry()];
      const query: PatternReuseQuery = { intentText: 'fix typescript imports' };
      const vm = buildPatternReuseHintViewModel(entries, query);
      expect(vm.hasMatches).toBe(true);
      expect(vm.matchCount).toBeGreaterThan(0);
      expect(vm.hintText.length).toBeGreaterThan(0);
      expect(Array.isArray(vm.actions)).toBe(true);
    });

    it('builds a view model with no matches', () => {
      const vm = buildPatternReuseHintViewModel([], { intentText: 'deploy production' });
      expect(vm.hasMatches).toBe(false);
      expect(vm.matchCount).toBe(0);
      expect(vm.hintText).toContain('kein');
      expect(vm.actions).toHaveLength(0);
    });
  });
});
