import { describe, expect, it } from 'vitest';
import {
  CONTAINER_INTELLIGENCE_PATTERN_RULES,
  getPatternRulesForContainer,
  getPatternRuleById,
  getAllContainerPatternRules,
  getContainerIdsWithPatterns,
  assertContainerPatternRulesValid,
} from './containerIntelligencePatternRules';
import { assertContainerDecisionRulesValid, decideContainerAction } from './containerDecisionGrammar';

describe('containerIntelligencePatternRules', () => {
  describe('CONTAINER_INTELLIGENCE_PATTERN_RULES', () => {
    it('contains pattern rules for all known containers', () => {
      const containerIds = getContainerIdsWithPatterns();
      expect(containerIds.length).toBeGreaterThanOrEqual(14);
      expect(containerIds).toContain('repo-snapshot');
      expect(containerIds).toContain('builder');
      expect(containerIds).toContain('generated-files');
      expect(containerIds).toContain('diff-preview');
      expect(containerIds).toContain('workflow');
      expect(containerIds).toContain('remote-memory');
      expect(containerIds).toContain('pattern-memory');
      expect(containerIds).toContain('telemetry');
      expect(containerIds).toContain('health');
      expect(containerIds).toContain('runtime-coverage');
      expect(containerIds).toContain('findings');
      expect(containerIds).toContain('sequential-runtime');
      expect(containerIds).toContain('mobile-workbench');
      expect(containerIds).toContain('mobile-coach');
    });

    it('has more than 50 pattern rules', () => {
      expect(CONTAINER_INTELLIGENCE_PATTERN_RULES.length).toBeGreaterThan(50);
    });

    it('all rules are valid container decision rules', () => {
      expect(() => assertContainerDecisionRulesValid(CONTAINER_INTELLIGENCE_PATTERN_RULES)).not.toThrow();
    });

    it('no duplicate rule IDs', () => {
      const ids = CONTAINER_INTELLIGENCE_PATTERN_RULES.map((r) => r.id);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });

    it('each container has at least 3 pattern rules', () => {
      const containerIds = getContainerIdsWithPatterns();
      for (const containerId of containerIds) {
        const rules = getPatternRulesForContainer(containerId);
        expect(rules.length).toBeGreaterThanOrEqual(3);
      }
    });

    it('each rule has valid lamp and action', () => {
      const validLamps = ['green', 'yellow', 'red'];
      const validActions = ['continue', 'ask-user', 'review', 'repair', 'learn'];
      for (const rule of CONTAINER_INTELLIGENCE_PATTERN_RULES) {
        expect(validLamps).toContain(rule.lamp);
        expect(validActions).toContain(rule.action);
      }
    });

    it('each rule has learnTag and nextAction', () => {
      for (const rule of CONTAINER_INTELLIGENCE_PATTERN_RULES) {
        expect(rule.learnTag.trim().length).toBeGreaterThan(0);
        expect(rule.nextAction.trim().length).toBeGreaterThan(0);
        expect(rule.learnTag).toContain(rule.containerId);
      }
    });
  });

  describe('getPatternRulesForContainer', () => {
    it('returns rules for repo-snapshot', () => {
      const rules = getPatternRulesForContainer('repo-snapshot');
      expect(rules.length).toBeGreaterThan(3);
      expect(rules.every((r) => r.containerId === 'repo-snapshot')).toBe(true);
    });

    it('returns rules for builder', () => {
      const rules = getPatternRulesForContainer('builder');
      expect(rules.length).toBeGreaterThan(3);
      expect(rules.every((r) => r.containerId === 'builder')).toBe(true);
    });

    it('returns rules for mobile-workbench', () => {
      const rules = getPatternRulesForContainer('mobile-workbench');
      expect(rules.length).toBeGreaterThan(3);
    });

    it('returns empty array for unknown container', () => {
      const rules = getPatternRulesForContainer('non-existent-container');
      expect(rules).toHaveLength(0);
    });
  });

  describe('getPatternRuleById', () => {
    it('finds repo-snapshot:ready rule', () => {
      const rule = getPatternRuleById('repo-snapshot:ready');
      expect(rule).toBeDefined();
      expect(rule?.containerId).toBe('repo-snapshot');
      expect(rule?.lamp).toBe('green');
    });

    it('finds builder:goal-missing rule', () => {
      const rule = getPatternRuleById('builder:goal-missing');
      expect(rule).toBeDefined();
      expect(rule?.containerId).toBe('builder');
      expect(rule?.lamp).toBe('yellow');
    });

    it('returns undefined for unknown rule', () => {
      const rule = getPatternRuleById('non-existent-rule-id');
      expect(rule).toBeUndefined();
    });
  });

  describe('getAllContainerPatternRules', () => {
    it('returns all rules', () => {
      const allRules = getAllContainerPatternRules();
      expect(allRules.length).toBe(CONTAINER_INTELLIGENCE_PATTERN_RULES.length);
    });

    it('returns a copy, not the original array', () => {
      const allRules = getAllContainerPatternRules();
      allRules.push({} as any);
      expect(getAllContainerPatternRules().length).toBe(CONTAINER_INTELLIGENCE_PATTERN_RULES.length);
    });
  });

  describe('getContainerIdsWithPatterns', () => {
    it('returns all container IDs with patterns', () => {
      const ids = getContainerIdsWithPatterns();
      expect(ids.length).toBeGreaterThanOrEqual(14);
    });

    it('returns unique container IDs', () => {
      const ids = getContainerIdsWithPatterns();
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });
  });

  describe('assertContainerPatternRulesValid', () => {
    it('does not throw for valid rules', () => {
      expect(() => assertContainerPatternRulesValid()).not.toThrow();
    });
  });

  describe('decideContainerAction with pattern rules', () => {
    it('selects repo-snapshot:ready when repo is ready', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo ready and working', getPatternRulesForContainer('repo-snapshot'));
      expect(decision.lamp).toBe('green');
      expect(decision.action).toBe('continue');
    });

    it('selects repo-snapshot:missing when repo is missing', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo fehlt no repository loaded', getPatternRulesForContainer('repo-snapshot'));
      expect(decision.lamp).toBe('yellow');
      expect(decision.action).toBe('ask-user');
    });

    it('selects builder:ready when mission is ready', () => {
      const decision = decideContainerAction('builder', 'mission ready builder green', getPatternRulesForContainer('builder'));
      expect(decision.lamp).toBe('green');
    });

    it('selects builder:goal-missing when goal is not set', () => {
      const decision = decideContainerAction('builder', 'goal missing no mission set', getPatternRulesForContainer('builder'));
      expect(decision.lamp).toBe('yellow');
      expect(decision.action).toBe('ask-user');
    });

    it('selects generated-files:accepted when review passes', () => {
      const decision = decideContainerAction('generated-files', 'self review: accepted files ready', getPatternRulesForContainer('generated-files'));
      expect(decision.lamp).toBe('green');
    });

    it('selects workflow:red when checks fail', () => {
      const decision = decideContainerAction('workflow', 'workflow red checks failed', getPatternRulesForContainer('workflow'));
      expect(decision.lamp).toBe('red');
      expect(decision.action).toBe('repair');
    });

    it('selects mobile-workbench:active-work for active work', () => {
      const decision = decideContainerAction('mobile-workbench', 'active work currently working', getPatternRulesForContainer('mobile-workbench'));
      expect(decision.lamp).toBe('green');
    });

    it('selects mobile-workbench:real-stopper for blocker', () => {
      const decision = decideContainerAction('mobile-workbench', 'real stopper blocking error critical blocker', getPatternRulesForContainer('mobile-workbench'));
      expect(decision.lamp).toBe('red');
    });
  });

  describe('Repo Snapshot patterns', () => {
    it('has ready pattern', () => {
      const rule = getPatternRuleById('repo-snapshot:ready');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('green');
      expect(rule?.action).toBe('continue');
    });

    it('has missing pattern with ask-user action', () => {
      const rule = getPatternRuleById('repo-snapshot:missing');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('yellow');
      expect(rule?.action).toBe('ask-user');
    });

    it('has load-failed pattern with repair action', () => {
      const rule = getPatternRuleById('repo-snapshot:load-failed');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('red');
      expect(rule?.action).toBe('repair');
    });
  });

  describe('Builder patterns', () => {
    it('has goal-missing pattern with blockers', () => {
      const rule = getPatternRuleById('builder:goal-missing');
      expect(rule).toBeDefined();
      expect(rule?.blockers).toBeDefined();
      expect(rule?.blockers!.length).toBeGreaterThan(0);
    });

    it('has package-build-active pattern', () => {
      const rule = getPatternRuleById('builder:package-build-active');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('green');
    });
  });

  describe('Generated Files patterns', () => {
    it('has accepted and rejected patterns', () => {
      const accepted = getPatternRuleById('generated-files:accepted');
      const rejected = getPatternRuleById('generated-files:rejected');
      expect(accepted?.lamp).toBe('green');
      expect(rejected?.lamp).toBe('red');
    });

    it('has self-review-failed pattern', () => {
      const rule = getPatternRuleById('generated-files:self-review-failed');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('red');
    });
  });

  describe('Workflow patterns', () => {
    it('has pending, green, and red patterns', () => {
      const pending = getPatternRuleById('workflow:pending');
      const green = getPatternRuleById('workflow:green');
      const red = getPatternRuleById('workflow:red');
      expect(pending?.lamp).toBe('yellow');
      expect(green?.lamp).toBe('green');
      expect(red?.lamp).toBe('red');
    });
  });

  describe('Sequential Runtime patterns', () => {
    it('has active-step pattern', () => {
      const rule = getPatternRuleById('sequential-runtime:active-step');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('green');
    });

    it('has failed pattern', () => {
      const rule = getPatternRuleById('sequential-runtime:failed');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('red');
    });

    it('has blocked-transition pattern', () => {
      const rule = getPatternRuleById('sequential-runtime:blocked-transition');
      expect(rule).toBeDefined();
      expect(rule?.lamp).toBe('red');
    });
  });
});