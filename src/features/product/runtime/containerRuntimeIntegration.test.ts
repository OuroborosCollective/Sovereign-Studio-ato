/**
 * Container Runtime Integration Tests
 * Testet das Zusammenspiel der Container-Runtime-Komponenten
 */

import { describe, expect, it } from 'vitest';
import { decideContainerAction } from './containerDecisionGrammar';
import { createBaselineContainerDecisionRules } from './containerDecisionBaselineRules';
import { getPatternRulesForContainer, CONTAINER_INTELLIGENCE_PATTERN_RULES } from './containerIntelligencePatternRules';
import { buildContainerIntelligenceCoverageReport, listContainerIntelligenceGaps } from './containerIntelligenceCoverage';
import { decideMobileWorkflow } from '../../../mobile-workflow-orchestrator';
import { matchMobileWorkflowPattern } from '../../../mobile-workflow-pattern-rules';

describe('container runtime integration', () => {
  describe('decision pipeline: grammar + baseline rules', () => {
    const baselineRules = createBaselineContainerDecisionRules();

    it('uses baseline rules for repo-snapshot ready state', () => {
      // Baseline rules use hyphen format: "repo-snapshot ready"
      const decision = decideContainerAction('repo-snapshot', 'repo-snapshot ready', baselineRules);
      expect(decision.lamp).toBe('green');
      expect(decision.action).toBe('continue');
      expect(decision.learnTag).toContain('repo-snapshot');
    });

    it('uses baseline rules for repo-snapshot review state', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo-snapshot needs attention', baselineRules);
      expect(decision.lamp).toBe('yellow');
      expect(decision.action).toBe('review');
    });

    it('uses baseline rules for repo-snapshot repair state', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo-snapshot failed', baselineRules);
      expect(decision.lamp).toBe('red');
      expect(decision.action).toBe('repair');
    });

    it('uses baseline rules for builder ready state', () => {
      const decision = decideContainerAction('builder', 'builder ready and ok', baselineRules);
      expect(decision.lamp).toBe('green');
    });

    it('uses baseline rules for workflow red state', () => {
      const decision = decideContainerAction('workflow', 'workflow red and failed', baselineRules);
      expect(decision.lamp).toBe('red');
    });

    it('handles all 14 containers with baseline rules', () => {
      const containers = ['repo-snapshot', 'builder', 'generated-files', 'diff-preview', 'workflow', 'remote-memory', 'pattern-memory', 'telemetry', 'health', 'runtime-coverage', 'findings', 'sequential-runtime', 'mobile-workbench', 'mobile-coach'];
      for (const container of containers) {
        const decision = decideContainerAction(container, `${container} ready`, baselineRules);
        expect(decision.containerId).toBe(container);
        expect(['green', 'yellow', 'red']).toContain(decision.lamp);
      }
    });
  });

  describe('decision pipeline: grammar + pattern rules', () => {
    it('pattern rules override baseline for generated-files accepted', () => {
      const patternRules = getPatternRulesForContainer('generated-files');
      const decision = decideContainerAction('generated-files', 'self review: accepted files ready', patternRules);
      expect(decision.lamp).toBe('green');
      expect(decision.action).toBe('continue');
      expect(decision.matchedSignals.length).toBeGreaterThan(0);
    });

    it('pattern rules detect workflow failures', () => {
      const patternRules = getPatternRulesForContainer('workflow');
      const decision = decideContainerAction('workflow', 'workflow red checks failed test failed', patternRules);
      expect(decision.lamp).toBe('red');
      expect(decision.action).toBe('repair');
      expect(decision.ruleId).toBe('workflow:red');
    });

    it('pattern rules handle sequential runtime states', () => {
      const patternRules = getPatternRulesForContainer('sequential-runtime');
      
      const activeDecision = decideContainerAction('sequential-runtime', 'active step running', patternRules);
      expect(activeDecision.lamp).toBe('green');
      
      const blockedDecision = decideContainerAction('sequential-runtime', 'blocked transition cannot proceed', patternRules);
      expect(blockedDecision.lamp).toBe('red');
      
      const completedDecision = decideContainerAction('sequential-runtime', 'completed all steps done', patternRules);
      expect(completedDecision.lamp).toBe('green');
    });

    it('all 80+ pattern rules are loadable and valid', () => {
      expect(CONTAINER_INTELLIGENCE_PATTERN_RULES.length).toBeGreaterThan(80);
      for (const rule of CONTAINER_INTELLIGENCE_PATTERN_RULES) {
        expect(rule.id).toBeTruthy();
        expect(rule.containerId).toBeTruthy();
        expect(rule.signals.length).toBeGreaterThan(0);
        expect(['green', 'yellow', 'red']).toContain(rule.lamp);
      }
    });
  });

  describe('mobile workflow integration', () => {
    it('active sequential package-build shows Builder/Workbench', () => {
      const decision = decideMobileWorkflow({ visibleText: 'package-build running is building' });
      expect(decision.mode).toBe('matrix-work');
      expect(decision.targetNav).toBeTruthy();
    });

    it('self-review accepted shows Files', () => {
      const decision = decideMobileWorkflow({ visibleText: 'SELF REVIEW: ACCEPTED generated-output-accepted' });
      expect(decision.mode).toBe('review-log');
      expect(decision.targetNav).toBe('Files');
      expect(decision.lamp).toBe('green');
    });

    it('workflow red shows Monitor/Repair', () => {
      const decision = decideMobileWorkflow({ visibleText: 'workflow failed validation_failed build failed' });
      expect(decision.lamp).toBe('red');
      expect(decision.mode).toBe('repair-log');
    });

    it('repo missing shows Repo/Setup', () => {
      const decision = decideMobileWorkflow({ visibleText: 'repo fehlt noch kein echtes repo' });
      expect(decision.lamp).toBe('yellow');
      expect(decision.targetNav).toBe('Repo');
    });

    it('0 failed does not trigger real-stopper', () => {
      const decision = decideMobileWorkflow({ visibleText: 'no active step; 0 completed step(s), 0 failed step(s) runtime ready' });
      expect(decision.lamp).not.toBe('red');
    });

    it('no false red with healthy runtime', () => {
      const decision = decideMobileWorkflow({ visibleText: 'runtime validation coverage healthy 21/21 runtime validation' });
      expect(decision.lamp).toBe('green');
    });

    it('awaiting-intent shows Builder', () => {
      const match = matchMobileWorkflowPattern('ready for next task');
      expect(match.rule.id).toBe('awaiting-intent');
    });
  });

  describe('coverage registry integration', () => {
    it('registry is valid', () => {
      const report = buildContainerIntelligenceCoverageReport();
      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
    });

    it('has gaps to fill', () => {
      const gaps = listContainerIntelligenceGaps();
      expect(gaps.length).toBeGreaterThan(0);
    });

    it('has covered containers as reference', () => {
      const report = buildContainerIntelligenceCoverageReport();
      const covered = report.entries.filter((e) => e.status === 'covered');
      expect(covered.length).toBeGreaterThan(0);
      expect(covered.some((e) => e.id === 'generated-files')).toBe(true);
    });

    it('mobile-workbench is covered', () => {
      const report = buildContainerIntelligenceCoverageReport();
      const mobileWorkbench = report.entries.find((e) => e.id === 'mobile-workbench');
      expect(mobileWorkbench?.status).toBe('covered');
    });

    it('bridge-validation is covered', () => {
      const report = buildContainerIntelligenceCoverageReport();
      const bridge = report.entries.find((e) => e.id === 'bridge-validation');
      expect(bridge?.status).toBe('covered');
    });

    it('all containers have nextAction for gaps', () => {
      const gaps = listContainerIntelligenceGaps();
      for (const gap of gaps) {
        expect(gap.nextAction.trim().length).toBeGreaterThan(0);
      }
    });
  });

  describe('end-to-end scenario: successful file generation flow', () => {
    it('repo-ready → builder-ready → files-accepted → diff-ready', () => {
      const patternRules = getPatternRulesForContainer('repo-snapshot');
      const repoDecision = decideContainerAction('repo-snapshot', 'repo ready snapshot loaded', patternRules);
      expect(repoDecision.lamp).toBe('green');
      expect(repoDecision.action).toBe('continue');

      const builderRules = getPatternRulesForContainer('builder');
      const builderDecision = decideContainerAction('builder', 'mission ready builder green package build active', builderRules);
      expect(builderDecision.lamp).toBe('green');

      const filesRules = getPatternRulesForContainer('generated-files');
      const filesDecision = decideContainerAction('generated-files', 'self review: accepted generated output ready', filesRules);
      expect(filesDecision.lamp).toBe('green');
      expect(filesDecision.action).toBe('continue');

      const diffRules = getPatternRulesForContainer('diff-preview');
      const diffDecision = decideContainerAction('diff-preview', 'diff ready diff preview ready', diffRules);
      expect(diffDecision.lamp).toBe('green');
    });
  });

  describe('end-to-end scenario: repair flow', () => {
    it('workflow-red → findings-critical → sequential-runtime-blocked', () => {
      const workflowRules = getPatternRulesForContainer('workflow');
      const workflowDecision = decideContainerAction('workflow', 'workflow red checks failed build failed', workflowRules);
      expect(workflowDecision.lamp).toBe('red');
      expect(workflowDecision.action).toBe('repair');

      const findingsRules = getPatternRulesForContainer('findings');
      const findingsDecision = decideContainerAction('findings', 'finding critical blocking issue must fix', findingsRules);
      expect(findingsDecision.lamp).toBe('red');
      expect(findingsDecision.action).toBe('repair');

      const seqRules = getPatternRulesForContainer('sequential-runtime');
      const seqDecision = decideContainerAction('sequential-runtime', 'blocked transition cannot proceed step blocked', seqRules);
      expect(seqDecision.lamp).toBe('red');
      expect(seqDecision.action).toBe('repair');
    });
  });
});