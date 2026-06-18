import { describe, expect, it } from 'vitest';
import { createBaselineContainerDecisionRules, CONTAINER_DECISION_IDS } from './containerDecisionBaselineRules';
import { assertContainerDecisionRulesValid } from './containerDecisionGrammar';

describe('containerDecisionBaselineRules', () => {
  describe('CONTAINER_DECISION_IDS', () => {
    it('contains at least 14 container IDs', () => {
      expect(CONTAINER_DECISION_IDS.length).toBeGreaterThanOrEqual(14);
    });

    it('includes key containers', () => {
      expect(CONTAINER_DECISION_IDS).toContain('repo-snapshot');
      expect(CONTAINER_DECISION_IDS).toContain('builder');
      expect(CONTAINER_DECISION_IDS).toContain('generated-files');
      expect(CONTAINER_DECISION_IDS).toContain('workflow');
      expect(CONTAINER_DECISION_IDS).toContain('telemetry');
      expect(CONTAINER_DECISION_IDS).toContain('remote-memory');
      expect(CONTAINER_DECISION_IDS).toContain('pattern-memory');
      expect(CONTAINER_DECISION_IDS).toContain('health');
      expect(CONTAINER_DECISION_IDS).toContain('runtime-coverage');
      expect(CONTAINER_DECISION_IDS).toContain('findings');
    });

    it('includes mobile containers', () => {
      expect(CONTAINER_DECISION_IDS).toContain('mobile-workbench');
      expect(CONTAINER_DECISION_IDS).toContain('mobile-coach');
    });

    it('includes sequential-runtime', () => {
      expect(CONTAINER_DECISION_IDS).toContain('sequential-runtime');
    });
  });

  describe('createBaselineContainerDecisionRules', () => {
    it('generates rules for all containers', () => {
      const rules = createBaselineContainerDecisionRules();
      const containerIds = [...new Set(rules.map((r) => r.containerId))];
      expect(containerIds.length).toBe(CONTAINER_DECISION_IDS.length);
    });

    it('generates ready, review, and repair rules per container', () => {
      const rules = createBaselineContainerDecisionRules(['repo-snapshot']);
      const ids = rules.map((r) => r.id);
      expect(ids).toContain('repo-snapshot:ready');
      expect(ids).toContain('repo-snapshot:review');
      expect(ids).toContain('repo-snapshot:repair');
    });

    it('creates 3 rules per container (ready, review, repair)', () => {
      const rules = createBaselineContainerDecisionRules(['builder', 'workflow']);
      expect(rules.length).toBe(6);
    });

    it('all generated rules are valid', () => {
      const rules = createBaselineContainerDecisionRules();
      expect(() => assertContainerDecisionRulesValid(rules)).not.toThrow();
    });

    it('no duplicate rule ids across all containers', () => {
      const rules = createBaselineContainerDecisionRules();
      const ids = rules.map((r) => r.id);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });

    it('ready rules have green lamp and continue action', () => {
      const rules = createBaselineContainerDecisionRules();
      const readyRules = rules.filter((r) => r.id.endsWith(':ready'));
      expect(readyRules.every((r) => r.lamp === 'green')).toBe(true);
      expect(readyRules.every((r) => r.action === 'continue')).toBe(true);
    });

    it('review rules have yellow lamp and review action', () => {
      const rules = createBaselineContainerDecisionRules();
      const reviewRules = rules.filter((r) => r.id.endsWith(':review'));
      expect(reviewRules.every((r) => r.lamp === 'yellow')).toBe(true);
      expect(reviewRules.every((r) => r.action === 'review')).toBe(true);
    });

    it('repair rules have red lamp and repair action', () => {
      const rules = createBaselineContainerDecisionRules();
      const repairRules = rules.filter((r) => r.id.endsWith(':repair'));
      expect(repairRules.every((r) => r.lamp === 'red')).toBe(true);
      expect(repairRules.every((r) => r.action === 'repair')).toBe(true);
    });

    it('each container has at least ready and review rules', () => {
      const rules = createBaselineContainerDecisionRules();
      for (const containerId of CONTAINER_DECISION_IDS) {
        const containerRules = rules.filter((r) => r.containerId === containerId);
        expect(containerRules.length).toBeGreaterThanOrEqual(2);
        expect(containerRules.some((r) => r.lamp === 'green')).toBe(true);
        expect(containerRules.some((r) => r.lamp === 'yellow')).toBe(true);
      }
    });

    it('baseline covers key containers: Repo/Builder/Generated/Workflow/Telemetry', () => {
      const rules = createBaselineContainerDecisionRules();
      const coveredContainers = ['repo-snapshot', 'builder', 'generated-files', 'workflow', 'telemetry'];
      for (const containerId of coveredContainers) {
        const containerRules = rules.filter((r) => r.containerId === containerId);
        expect(containerRules.length).toBeGreaterThan(0);
      }
    });

    it('baseline covers Remote/Pattern/Health/Coverage/Findings', () => {
      const rules = createBaselineContainerDecisionRules();
      const coveredContainers = ['remote-memory', 'pattern-memory', 'health', 'runtime-coverage', 'findings'];
      for (const containerId of coveredContainers) {
        const containerRules = rules.filter((r) => r.containerId === containerId);
        expect(containerRules.length).toBeGreaterThan(0);
      }
    });

    it('all rules have learnTag matching container ID', () => {
      const rules = createBaselineContainerDecisionRules();
      for (const rule of rules) {
        expect(rule.learnTag).toContain(rule.containerId);
      }
    });

    it('all rules have non-empty nextAction', () => {
      const rules = createBaselineContainerDecisionRules();
      expect(rules.every((r) => r.nextAction.trim().length > 0)).toBe(true);
    });
  });
});