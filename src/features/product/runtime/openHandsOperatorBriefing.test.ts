import { describe, expect, it } from 'vitest';
import {
  buildOpenHandsOperatorBriefing,
  BRIEFING_STATUS_COLORS,
  BRIEFING_STATUS_LABELS,
  summarizeOpenHandsBriefing,
} from './openHandsOperatorBriefing';

describe('openHandsOperatorBriefing', () => {
  describe('buildOpenHandsOperatorBriefing', () => {
    it('returns all sections when OpenHands is disabled', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: false,
        deploymentMode: 'disabled',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'OpenHands is disabled.',
      });

      expect(briefing.sections).toHaveLength(5);
      expect(briefing.sections.map(s => s.id)).toEqual([
        'triggers',
        'workflows',
        'output',
        'configuration',
        'secrets',
      ]);
      expect(briefing.blockedCount).toBeGreaterThan(0);
      expect(briefing.isBlocked).toBe(true);
    });

    it('returns all sections when OpenHands is ready', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: 'https://openhands.example.com/api',
        adminConsoleUrl: 'https://openhands.example.com/admin',
        ready: true,
        reason: 'Ready.',
      });

      expect(briefing.sections).toHaveLength(5);
      expect(briefing.blockedCount).toBe(0);
      expect(briefing.warningCount).toBe(0);
      expect(briefing.isBlocked).toBe(false);
    });

    it('flags missing Agent API URL as blocked', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: '',
        adminConsoleUrl: 'https://openhands.example.com/admin',
        ready: false,
        reason: 'Agent API URL missing.',
      });

      const configSection = briefing.sections.find(s => s.id === 'configuration');
      const agentApiItem = configSection?.items.find(i => i.id === 'agent-api-url');
      expect(agentApiItem?.status).toBe('blocked');
      expect(agentApiItem?.value).toBe('Fehlt');
    });

    it('flags missing Admin Console URL as warning only', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: 'https://openhands.example.com/api',
        adminConsoleUrl: '',
        ready: true,
        reason: 'Ready.',
      });

      const configSection = briefing.sections.find(s => s.id === 'configuration');
      const adminConsoleItem = configSection?.items.find(i => i.id === 'admin-console-url');
      expect(adminConsoleItem?.status).toBe('warning');
      expect(adminConsoleItem?.value).toBe('Fehlt');
    });

    it('flags HTTP URLs as blocked except localhost', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: 'http://openhands.example.com/api',
        adminConsoleUrl: 'https://openhands.example.com/admin',
        ready: false,
        reason: 'HTTP not allowed outside localhost.',
      });

      const configSection = briefing.sections.find(s => s.id === 'configuration');
      const httpsItem = configSection?.items.find(i => i.id === 'https-required');
      expect(httpsItem?.status).toBe('blocked');
    });

    it('allows localhost HTTP URLs', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: 'http://localhost:8080/api',
        adminConsoleUrl: '',
        ready: true,
        reason: 'Ready.',
      });

      const configSection = briefing.sections.find(s => s.id === 'configuration');
      const httpsItem = configSection?.items.find(i => i.id === 'https-required');
      expect(httpsItem?.status).toBe('ok');
      expect(httpsItem?.value).toContain('localhost');
    });

    it('flags missing secrets in secrets section', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Config not ready.',
      });

      const secretsSection = briefing.sections.find(s => s.id === 'secrets');
      const missingItems = secretsSection?.items.filter(i => i.status === 'blocked' || i.status === 'warning');
      expect(missingItems?.length).toBeGreaterThan(0);
    });
  });

  describe('summarizeOpenHandsBriefing', () => {
    it('reports blocked count when briefing is blocked', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: false,
        deploymentMode: 'disabled',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Disabled.',
      });

      const summary = summarizeOpenHandsBriefing(briefing);
      expect(summary).toContain('blockierende');
      expect(summary).toContain(String(briefing.blockedCount));
    });

    it('reports warning count when briefing has warnings', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: 'https://openhands.example.com/api',
        adminConsoleUrl: '',
        ready: true,
        reason: 'Ready.',
      });

      const summary = summarizeOpenHandsBriefing(briefing);
      expect(summary).toContain('Warnung');
    });

    it('reports ready when fully configured', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'external-agent-runtime',
        agentApiUrl: 'https://openhands.example.com/api',
        adminConsoleUrl: 'https://openhands.example.com/admin',
        ready: true,
        reason: 'Ready.',
      });

      const summary = summarizeOpenHandsBriefing(briefing);
      expect(summary).toContain('vollständig konfiguriert');
      expect(summary).toContain('bereit');
    });
  });

  describe('status constants', () => {
    it('has correct status colors', () => {
      expect(BRIEFING_STATUS_COLORS.ok).toBe('#34d399');
      expect(BRIEFING_STATUS_COLORS.warning).toBe('#fbbf24');
      expect(BRIEFING_STATUS_COLORS.blocked).toBe('#fb7185');
      expect(BRIEFING_STATUS_COLORS.info).toBe('#22d3ee');
    });

    it('has correct status labels', () => {
      expect(BRIEFING_STATUS_LABELS.ok).toBe('OK');
      expect(BRIEFING_STATUS_LABELS.warning).toBe('Warnung');
      expect(BRIEFING_STATUS_LABELS.blocked).toBe('Blockiert');
      expect(BRIEFING_STATUS_LABELS.info).toBe('Info');
    });
  });

  describe('trigger section', () => {
    it('contains start labels', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: false,
        deploymentMode: 'disabled',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Disabled.',
      });

      const triggerSection = briefing.sections.find(s => s.id === 'triggers');
      const labelsItem = triggerSection?.items.find(i => i.id === 'labels');
      expect(labelsItem?.value).toContain('openhands-review');
      expect(labelsItem?.value).toContain('openhands-agent');
      expect(labelsItem?.status).toBe('info');
    });

    it('contains comment marker', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: false,
        deploymentMode: 'disabled',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Disabled.',
      });

      const triggerSection = briefing.sections.find(s => s.id === 'triggers');
      const markerItem = triggerSection?.items.find(i => i.id === 'comment-marker');
      expect(markerItem?.value).toBe('/openhands');
    });
  });

  describe('workflow section', () => {
    it('contains workflow information', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: false,
        deploymentMode: 'disabled',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Disabled.',
      });

      const workflowSection = briefing.sections.find(s => s.id === 'workflows');
      expect(workflowSection?.items).toHaveLength(3);
      expect(workflowSection?.items.every(i => i.status === 'ok')).toBe(true);
    });
  });

  describe('output section', () => {
    it('contains output type information', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: false,
        deploymentMode: 'disabled',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Disabled.',
      });

      const outputSection = briefing.sections.find(s => s.id === 'output');
      const draftPrItem = outputSection?.items.find(i => i.id === 'draft-pr');
      const branchItem = outputSection?.items.find(i => i.id === 'branch');
      expect(draftPrItem?.value).toBe('Ja');
      expect(branchItem?.value).toBe('Ja');
    });
  });

  describe('sovereign-agent-backend mode', () => {
    it('shows sovereign-agent-backend as ready mode', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'sovereign-agent-backend',
        agentApiUrl: 'https://sovereign-backend.example/api/agent',
        adminConsoleUrl: '',
        ready: true,
        reason: 'Sovereign Agent Backend is configured as the primary internal runtime.',
      });

      expect(briefing.sections).toHaveLength(5);
      expect(briefing.blockedCount).toBe(0);
      expect(briefing.isBlocked).toBe(false);
    });

    it('flags missing sovereign backend URL as blocked', () => {
      const briefing = buildOpenHandsOperatorBriefing({
        enabled: true,
        deploymentMode: 'sovereign-agent-backend',
        agentApiUrl: '',
        adminConsoleUrl: '',
        ready: false,
        reason: 'Agent API URL missing.',
      });

      const configSection = briefing.sections.find(s => s.id === 'configuration');
      const agentApiItem = configSection?.items.find(i => i.id === 'agent-api-url');
      expect(agentApiItem?.status).toBe('blocked');
    });
  });
});