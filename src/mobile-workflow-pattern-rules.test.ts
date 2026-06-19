import { describe, expect, it } from 'vitest';

import {
  MOBILE_WORKFLOW_PATTERN_RULES,
  assertMobileWorkflowPatternRulesValid,
  createMobileWorkflowPatternLearningReport,
  createMobileWorkflowPatternRulesWithOverrides,
  getMobileWorkflowPatternRulesHealth,
  matchMobileWorkflowPattern,
  matchMobileWorkflowPatternDetailed,
  normalizeMobileWorkflowText,
  validateMobileWorkflowPatternRule,
  validateMobileWorkflowPatternRules,
  type MobileWorkflowPatternRule,
} from './mobile-workflow-pattern-rules';

function cloneRules(): MobileWorkflowPatternRule[] {
  return MOBILE_WORKFLOW_PATTERN_RULES.map((rule) => ({
    ...rule,
    positiveSignals: [...rule.positiveSignals],
    negativeSignals: rule.negativeSignals ? [...rule.negativeSignals] : undefined,
    lines: [...rule.lines],
  }));
}

function ruleById(
  rules: MobileWorkflowPatternRule[],
  id: MobileWorkflowPatternRule['id'],
): MobileWorkflowPatternRule {
  const rule = rules.find((candidate) => candidate.id === id);

  if (!rule) {
    throw new Error(`expected rule ${id} to exist`);
  }

  return rule;
}

describe('mobile workflow pattern rules', () => {
  describe('bundled rule contract', () => {
    it('keeps the bundled pattern rules valid and healthy', () => {
      expect(() => assertMobileWorkflowPatternRulesValid()).not.toThrow();

      const report = validateMobileWorkflowPatternRules();
      const health = getMobileWorkflowPatternRulesHealth();

      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
      expect(Array.isArray(report.warnings)).toBe(true);

      expect(health.valid).toBe(true);
      expect(health.ruleCount).toBe(MOBILE_WORKFLOW_PATTERN_RULES.length);
      expect(health.fallbackPresent).toBe(true);
      expect(health.fallbackPriorityLowest).toBe(true);
      expect(health.ids).toContain('awaiting-intent');
    });

    it('keeps exactly one fallback rule and keeps it passive', () => {
      const fallbackRules = MOBILE_WORKFLOW_PATTERN_RULES.filter(
        (rule) => rule.id === 'awaiting-intent',
      );

      expect(fallbackRules).toHaveLength(1);

      const fallback = fallbackRules[0];

      expect(fallback.priority).toBeLessThan(
        Math.min(
          ...MOBILE_WORKFLOW_PATTERN_RULES.filter(
            (rule) => rule.id !== 'awaiting-intent',
          ).map((rule) => rule.priority),
        ),
      );
      expect(fallback.positiveSignals).toEqual([]);
      expect(fallback.minScore).toBe(0);
      expect(fallback.autoOpenTarget).toBe(false);
      expect(fallback.targetNav).toBe('Builder');
    });

    it('keeps every rule wired to visible workbench lines', () => {
      for (const rule of MOBILE_WORKFLOW_PATTERN_RULES) {
        expect(rule.lines.length).toBeGreaterThan(0);
        expect(rule.lines.join('\n')).toContain(`pattern = ${rule.id}`);
        expect(rule.title.trim()).not.toBe('');
        expect(rule.summary.trim()).not.toBe('');
      }
    });

    it('keeps ids unique and priorities finite', () => {
      const ids = MOBILE_WORKFLOW_PATTERN_RULES.map((rule) => rule.id);

      expect(new Set(ids).size).toBe(ids.length);

      for (const rule of MOBILE_WORKFLOW_PATTERN_RULES) {
        expect(Number.isFinite(rule.priority)).toBe(true);
        expect(rule.priority).toBeGreaterThanOrEqual(0);
      }
    });
  });

  describe('normalization', () => {
    it('normalizes German umlauts, separators, case, and whitespace consistently', () => {
      expect(normalizeMobileWorkflowText('  LÄUFT_package-build__FEHLGESCHLAGEN  ')).toBe(
        'laeuft package build fehlgeschlagen',
      );

      expect(normalizeMobileWorkflowText('Grün   läuft — Build_Check')).toBe(
        'gruen laeuft build check',
      );
    });

    it('matches using normalized text instead of raw case or separator shape', () => {
      const activeMatch = matchMobileWorkflowPattern('Paket LÄUFT_package-build');
      const stopperMatch = matchMobileWorkflowPattern('Build ist FEHLGESCHLAGEN');

      expect(activeMatch.rule.id).toBe('active-work');
      expect(stopperMatch.rule.id).toBe('real-stopper');
    });
  });

  describe('pattern matching', () => {
    it('selects active work over the fallback pattern', () => {
      const match = matchMobileWorkflowPattern('package-build package build running');

      expect(match.rule.id).toBe('active-work');
      expect(match.rule.mode).toBe('matrix-work');
      expect(match.rule.targetNav).toBe('Live Monitor');
      expect(match.score).toBeGreaterThanOrEqual(1);
      expect(match.matchedSignals.length).toBeGreaterThanOrEqual(1);
    });

    it('selects real stopper before active work when failure and running text coexist', () => {
      const match = matchMobileWorkflowPattern(
        'running package build failed with exit code 1',
      );

      expect(match.rule.id).toBe('real-stopper');
      expect(match.rule.lamp).toBe('red');
      expect(match.rule.mode).toBe('repair-log');
      expect(match.rule.autoOpenTarget).toBe(true);
    });

    it('selects review when generated output was accepted', () => {
      const match = matchMobileWorkflowPattern(
        'SELF REVIEW: ACCEPTED generated-output-accepted',
      );

      expect(match.rule.id).toBe('result-review');
      expect(match.rule.targetNav).toBe('Files');
      expect(match.rule.mode).toBe('review-log');
    });

    it('selects repo setup when a real repository snapshot is missing', () => {
      const match = matchMobileWorkflowPattern(
        'automation needs a loaded repository snapshot before full auto',
      );

      expect(match.rule.id).toBe('repo-setup');
      expect(match.rule.targetNav).toBe('Repo');
      expect(match.rule.lamp).toBe('yellow');
    });

    it('selects runtime healthy for clean green gate text', () => {
      const match = matchMobileWorkflowPattern(
        'green gate passed all checks passed build successful working tree clean',
      );

      expect(match.rule.id).toBe('runtime-healthy');
      expect(match.rule.lamp).toBe('green');
      expect(match.rule.autoOpenTarget).toBe(false);
    });

    it('does not select runtime healthy when failure text is present', () => {
      const match = matchMobileWorkflowPattern(
        'green gate passed but build failed critical blocker',
      );

      expect(match.rule.id).toBe('real-stopper');
      expect(match.rule.id).not.toBe('runtime-healthy');
    });

    it('does not select a stopper when harmless zero-failed text is present', () => {
      const match = matchMobileWorkflowPattern('0 failed step runtime ready');

      expect(match.rule.id).not.toBe('real-stopper');
      expect(match.rule.id).toBe('awaiting-intent');
    });

    it('uses awaiting-intent as real fallback for empty text', () => {
      const match = matchMobileWorkflowPattern('   \n\t   ');

      expect(match.rule.id).toBe('awaiting-intent');
      expect(match.score).toBe(0);
      expect(match.matchedSignals).toEqual([]);
    });

    it('uses awaiting-intent when no active rule reaches minScore', () => {
      const match = matchMobileWorkflowPattern('nur ein normaler Auftrag ohne runtime signal');

      expect(match.rule.id).toBe('awaiting-intent');
      expect(match.score).toBe(0);
      expect(match.matchedSignals).toEqual([]);
    });

    it('uses deterministic tie-breaks for equal priority and equal score', () => {
      const rules = cloneRules().map((rule) => {
        if (rule.id === 'active-work' || rule.id === 'repo-setup') {
          return {
            ...rule,
            priority: 77,
            positiveSignals: ['same deterministic signal'],
            negativeSignals: [],
            minScore: 1,
          };
        }

        if (rule.id !== 'awaiting-intent') {
          return {
            ...rule,
            positiveSignals: ['unmatched-token'],
            negativeSignals: [],
            minScore: 1,
          };
        }

        return rule;
      });

      const match = matchMobileWorkflowPattern('same deterministic signal', rules);

      expect(match.rule.id).toBe('active-work');
    });
  });

  describe('detailed matching', () => {
    it('returns detailed match explanation for selected pattern', () => {
      const detailed = matchMobileWorkflowPatternDetailed(
        'draft pr failed while workflow watch was running',
      );

      expect(detailed.rule.id).toBe('real-stopper');
      expect(detailed.score).toBeGreaterThanOrEqual(1);
      expect(detailed.candidates.length).toBe(MOBILE_WORKFLOW_PATTERN_RULES.length);
      expect(Array.isArray(detailed.rejectedCandidates)).toBe(true);

      expect(detailed.explanation.fallbackUsed).toBe(false);
      expect(detailed.explanation.selectedRuleId).toBe('real-stopper');
      expect(detailed.explanation.sourceHash).toMatch(/^mwf-[a-f0-9]{8}$/);
      expect(detailed.explanation.sourceLength).toBeGreaterThan(0);
      expect(detailed.explanation.normalizedSourceLength).toBeGreaterThan(0);
      expect(detailed.explanation.reason).toContain('Selected real-stopper');
    });

    it('returns detailed fallback explanation when no active rule matches', () => {
      const detailed = matchMobileWorkflowPatternDetailed('nur ein normaler Auftrag');

      expect(detailed.rule.id).toBe('awaiting-intent');
      expect(detailed.score).toBe(0);
      expect(detailed.matchedSignals).toEqual([]);
      expect(detailed.explanation.fallbackUsed).toBe(true);
      expect(detailed.explanation.selectedRuleId).toBe('awaiting-intent');
      expect(detailed.explanation.reason).toContain('fallback awaiting-intent selected');
      expect(detailed.candidates.length).toBe(MOBILE_WORKFLOW_PATTERN_RULES.length);
    });

    it('marks blocked candidates when negative signals are present', () => {
      const detailed = matchMobileWorkflowPatternDetailed(
        'runtime validation coverage healthy but build failed',
      );

      const healthyCandidate = detailed.candidates.find(
        (candidate) => candidate.rule.id === 'runtime-healthy',
      );

      expect(healthyCandidate).toBeDefined();
      expect(healthyCandidate?.blocked).toBe(true);
      expect(healthyCandidate?.blockedBySignals.length).toBeGreaterThan(0);
      expect(detailed.rule.id).toBe('real-stopper');
    });

    it('keeps selected match compatible with simple match API', () => {
      const text = 'generated package passed self review and diff ready';

      const simple = matchMobileWorkflowPattern(text);
      const detailed = matchMobileWorkflowPatternDetailed(text);

      expect(simple.rule.id).toBe(detailed.rule.id);
      expect(simple.score).toBe(detailed.score);
      expect(simple.matchedSignals).toEqual(detailed.matchedSignals);
    });

    it('produces stable source hash for equivalent normalized text', () => {
      const first = matchMobileWorkflowPatternDetailed('LÄUFT_package-build');
      const second = matchMobileWorkflowPatternDetailed('laeuft package build');

      expect(first.explanation.sourceHash).toBe(second.explanation.sourceHash);
      expect(first.rule.id).toBe(second.rule.id);
    });
  });

  describe('validation', () => {
    it('rejects a malformed fallback rule', () => {
      const malformedRule: MobileWorkflowPatternRule = {
        id: 'awaiting-intent',
        priority: Number.NaN,
        lamp: 'yellow',
        mode: 'nocode-plan',
        targetNav: null,
        autoOpenTarget: true,
        title: '',
        summary: '',
        positiveSignals: ['must-not-exist-on-fallback'],
        minScore: -1,
        lines: [],
      };

      const report = validateMobileWorkflowPatternRule(malformedRule);

      expect(report.valid).toBe(false);
      expect(report.errors.length).toBeGreaterThan(0);
      expect(report.errors.join(' | ')).toContain('priority must be finite');
      expect(report.errors.join(' | ')).toContain('auto-open requires target');
      expect(report.errors.join(' | ')).toContain('title is required');
      expect(report.errors.join(' | ')).toContain('summary is required');
      expect(report.errors.join(' | ')).toContain(
        'Fallback pattern awaiting-intent must not use positive signals',
      );
    });

    it('rejects unknown enum-like fields at runtime validation boundary', () => {
      const malformedRule = {
        ...ruleById(cloneRules(), 'active-work'),
        id: 'unknown-pattern',
        lamp: 'blue',
        mode: 'unknown-mode',
        targetNav: 'UnknownTarget',
      } as unknown as MobileWorkflowPatternRule;

      const report = validateMobileWorkflowPatternRule(malformedRule);

      expect(report.valid).toBe(false);
      expect(report.errors.join(' | ')).toContain('has unknown id');
      expect(report.errors.join(' | ')).toContain('has unknown lamp');
      expect(report.errors.join(' | ')).toContain('has unknown mode');
      expect(report.errors.join(' | ')).toContain('has unknown target');
    });

    it('detects duplicate pattern ids at rule-set level', () => {
      const duplicateRules = [
        ...cloneRules(),
        { ...ruleById(cloneRules(), 'real-stopper') },
      ];

      const report = validateMobileWorkflowPatternRules(duplicateRules);

      expect(report.valid).toBe(false);
      expect(report.errors.join(' | ')).toContain('Duplicate pattern id: real-stopper');
      expect(() => assertMobileWorkflowPatternRulesValid(duplicateRules)).toThrow(
        'Mobile workflow pattern rules invalid',
      );
    });

    it('detects missing fallback at rule-set level', () => {
      const withoutFallback = cloneRules().filter((rule) => rule.id !== 'awaiting-intent');

      const report = validateMobileWorkflowPatternRules(withoutFallback);

      expect(report.valid).toBe(false);
      expect(report.errors.join(' | ')).toContain(
        'Fallback pattern awaiting-intent is required',
      );
    });

    it('detects fallback priority violations', () => {
      const rules = cloneRules().map((rule) =>
        rule.id === 'awaiting-intent'
          ? {
              ...rule,
              priority: 999,
            }
          : rule,
      );

      const report = validateMobileWorkflowPatternRules(rules);

      expect(report.valid).toBe(false);
      expect(report.errors.join(' | ')).toContain(
        'Fallback pattern awaiting-intent must have lower priority than all active patterns',
      );
    });

    it('detects overlapping positive and negative signals', () => {
      const overlapped = cloneRules().map((rule) =>
        rule.id === 'active-work'
          ? {
              ...rule,
              negativeSignals: [...(rule.negativeSignals ?? []), 'running'],
            }
          : rule,
      );

      const report = validateMobileWorkflowPatternRules(overlapped);

      expect(report.valid).toBe(false);
      expect(report.errors.join(' | ')).toContain(
        'Pattern active-work has overlapping positive and negative signals',
      );
    });

    it('reports duplicate signals as warnings instead of breaking the rule-set', () => {
      const duplicated = cloneRules().map((rule) =>
        rule.id === 'active-work'
          ? {
              ...rule,
              positiveSignals: [...rule.positiveSignals, 'running'],
            }
          : rule,
      );

      const report = validateMobileWorkflowPatternRules(duplicated);

      expect(report.valid).toBe(true);
      expect(report.warnings.join(' | ')).toContain(
        'Pattern active-work has duplicate positive signals',
      );
    });

    it('rejects active rule without positive signals or valid minScore', () => {
      const invalidActive: MobileWorkflowPatternRule = {
        ...ruleById(cloneRules(), 'active-work'),
        positiveSignals: [],
        minScore: 0,
      };

      const report = validateMobileWorkflowPatternRule(invalidActive);

      expect(report.valid).toBe(false);
      expect(report.errors.join(' | ')).toContain('Pattern active-work needs positive signals');
      expect(report.errors.join(' | ')).toContain(
        'Pattern active-work minScore must be at least 1',
      );
    });
  });

  describe('overrides', () => {
    it('creates safe rule overrides without mutating bundled rules', () => {
      const originalRuntimeHealthy = ruleById(MOBILE_WORKFLOW_PATTERN_RULES, 'runtime-healthy');

      expect(originalRuntimeHealthy.positiveSignals).not.toContain('operator stabilisiert');

      const rules = createMobileWorkflowPatternRulesWithOverrides(
        MOBILE_WORKFLOW_PATTERN_RULES,
        [
          {
            id: 'runtime-healthy',
            addPositiveSignals: ['operator stabilisiert'],
          },
        ],
      );

      const match = matchMobileWorkflowPattern('operator stabilisiert', rules);

      expect(match.rule.id).toBe('runtime-healthy');
      expect(match.matchedSignals).toContain('operator stabilisiert');
      expect(originalRuntimeHealthy.positiveSignals).not.toContain('operator stabilisiert');
    });

    it('allows override removal of stale positive signals', () => {
      const rules = createMobileWorkflowPatternRulesWithOverrides(
        MOBILE_WORKFLOW_PATTERN_RULES,
        [
          {
            id: 'runtime-healthy',
            removePositiveSignals: ['healthy'],
            addPositiveSignals: ['system stable'],
          },
        ],
      );

      const fallbackMatch = matchMobileWorkflowPattern('healthy', rules);
      const stableMatch = matchMobileWorkflowPattern('system stable', rules);

      expect(fallbackMatch.rule.id).toBe('awaiting-intent');
      expect(stableMatch.rule.id).toBe('runtime-healthy');
    });

    it('allows override negative signals to suppress a noisy match', () => {
      const rules = createMobileWorkflowPatternRulesWithOverrides(
        MOBILE_WORKFLOW_PATTERN_RULES,
        [
          {
            id: 'active-work',
            addNegativeSignals: ['paused by operator'],
          },
        ],
      );

      const match = matchMobileWorkflowPattern('running paused by operator', rules);

      expect(match.rule.id).toBe('awaiting-intent');
    });

    it('rejects invalid overrides that break rule validity', () => {
      expect(() =>
        createMobileWorkflowPatternRulesWithOverrides(MOBILE_WORKFLOW_PATTERN_RULES, [
          {
            id: 'awaiting-intent',
            addPositiveSignals: ['bad fallback signal'],
          },
        ]),
      ).toThrow('Mobile workflow pattern rules invalid');

      expect(() =>
        createMobileWorkflowPatternRulesWithOverrides(MOBILE_WORKFLOW_PATTERN_RULES, [
          {
            id: 'runtime-healthy',
            minScore: 0,
          },
        ]),
      ).toThrow('Mobile workflow pattern rules invalid');

      expect(() =>
        createMobileWorkflowPatternRulesWithOverrides(MOBILE_WORKFLOW_PATTERN_RULES, [
          {
            id: 'active-work',
            addNegativeSignals: ['running'],
          },
        ]),
      ).toThrow('Mobile workflow pattern rules invalid');
    });

    it('keeps override-created rules valid and independent from later mutation of returned rules', () => {
      const rules = createMobileWorkflowPatternRulesWithOverrides(
        MOBILE_WORKFLOW_PATTERN_RULES,
        [
          {
            id: 'repo-setup',
            addPositiveSignals: ['bring repository online'],
          },
        ],
      );

      expect(validateMobileWorkflowPatternRules(rules).valid).toBe(true);

      ruleById(rules, 'repo-setup').positiveSignals.push('mutated-after-return');

      expect(ruleById(MOBILE_WORKFLOW_PATTERN_RULES, 'repo-setup').positiveSignals).not.toContain(
        'mutated-after-return',
      );
    });
  });

  describe('learning side-channel', () => {
    it('creates learning suggestions from mismatches without changing truth-path rules', () => {
      const report = createMobileWorkflowPatternLearningReport([
        {
          visibleText: 'operator stabilisiert alles sauber',
          expectedPatternId: 'runtime-healthy',
          operatorAccepted: false,
        },
        {
          visibleText: 'alles ist kaputt aber kein echter stopper',
          rejectedPatternId: 'real-stopper',
          operatorAccepted: false,
        },
      ]);

      expect(report.totalSignals).toBe(2);
      expect(report.usableSignals).toBe(2);
      expect(report.rejectedMatches).toBe(2);
      expect(report.suggestions.length).toBeGreaterThanOrEqual(1);
      expect(report.summary).toContain('usable learning signal');

      const healthySuggestion = report.suggestions.find(
        (suggestion) => suggestion.ruleId === 'runtime-healthy',
      );

      expect(healthySuggestion).toBeDefined();
      expect(healthySuggestion?.addPositiveSignals.length).toBeGreaterThan(0);

      const truthPathMatch = matchMobileWorkflowPattern('operator stabilisiert alles sauber');
      expect(truthPathMatch.rule.id).toBe('awaiting-intent');
    });

    it('creates negative learning suggestions for rejected patterns', () => {
      const report = createMobileWorkflowPatternLearningReport([
        {
          visibleText: 'running but user says do not open monitor',
          rejectedPatternId: 'active-work',
          operatorAccepted: false,
        },
      ]);

      const activeSuggestion = report.suggestions.find(
        (suggestion) => suggestion.ruleId === 'active-work',
      );

      expect(activeSuggestion).toBeDefined();
      expect(activeSuggestion?.addNegativeSignals.length).toBeGreaterThan(0);
      expect(report.rejectedMatches).toBe(1);
    });

    it('counts accepted matches without producing forced rule changes', () => {
      const report = createMobileWorkflowPatternLearningReport([
        {
          visibleText: 'package build running',
          expectedPatternId: 'active-work',
          operatorAccepted: true,
        },
      ]);

      expect(report.totalSignals).toBe(1);
      expect(report.usableSignals).toBe(1);
      expect(report.acceptedMatches).toBe(1);
      expect(report.mismatches).toBe(0);
      expect(report.suggestions).toEqual([]);
    });

    it('ignores empty learning signals safely', () => {
      const report = createMobileWorkflowPatternLearningReport([
        {
          visibleText: '',
          expectedPatternId: 'active-work',
        },
        {
          visibleText: '   ',
          rejectedPatternId: 'real-stopper',
        },
      ]);

      expect(report.totalSignals).toBe(2);
      expect(report.usableSignals).toBe(0);
      expect(report.suggestions).toEqual([]);
    });

    it('deduplicates learned suggestion terms', () => {
      const report = createMobileWorkflowPatternLearningReport([
        {
          visibleText: 'operator stabilisiert operator stabilisiert',
          expectedPatternId: 'runtime-healthy',
        },
        {
          visibleText: 'operator stabilisiert',
          expectedPatternId: 'runtime-healthy',
        },
      ]);

      const suggestion = report.suggestions.find(
        (candidate) => candidate.ruleId === 'runtime-healthy',
      );

      expect(suggestion).toBeDefined();

      const unique = new Set(suggestion?.addPositiveSignals ?? []);
      expect(unique.size).toBe(suggestion?.addPositiveSignals.length);
    });
  });
});
