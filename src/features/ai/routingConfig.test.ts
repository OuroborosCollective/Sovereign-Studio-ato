import { describe, it, expect } from 'vitest';
import {
  DEFAULT_ROUTES,
  getDefaultRoute,
  ROUTE_TO_COST_ID,
  type LlmRoute,
} from './routingConfig';

describe('routingConfig', () => {
  describe('DEFAULT_ROUTES', () => {
    it('contains all 5 required routes', () => {
      const ids = DEFAULT_ROUTES.map((r) => r.id);
      expect(ids).toContain('chat_standard');
      expect(ids).toContain('chat_pro');
      expect(ids).toContain('repo_analysis');
      expect(ids).toContain('draft_pr');
      expect(ids).toContain('vps_chat');
    });

    it('all routes have required fields', () => {
      for (const route of DEFAULT_ROUTES) {
        expect(route.id).toBeTruthy();
        expect(route.label).toBeTruthy();
        expect(route.defaultModelId).toBeTruthy();
        expect(route.creditsPerKTokens).toBeGreaterThan(0);
        expect(typeof route.enabled).toBe('boolean');
        expect(typeof route.userKeyOverride).toBe('boolean');
        expect(route.maxTokensPerRequest).toBeGreaterThan(0);
      }
    });

    it('chat_standard uses gemini-2.0-flash at 1 credit/1K tokens', () => {
      const r = DEFAULT_ROUTES.find((r) => r.id === 'chat_standard')!;
      expect(r.defaultModelId).toBe('gemini-2.0-flash');
      expect(r.creditsPerKTokens).toBe(1);
      expect(r.enabled).toBe(true);
      expect(r.userKeyOverride).toBe(true);
    });

    it('chat_pro uses gemini-2.5-pro at 8 credits/1K tokens', () => {
      const r = DEFAULT_ROUTES.find((r) => r.id === 'chat_pro')!;
      expect(r.defaultModelId).toBe('gemini-2.5-pro');
      expect(r.creditsPerKTokens).toBe(8);
    });

    it('repo_analysis does not allow user key override', () => {
      const r = DEFAULT_ROUTES.find((r) => r.id === 'repo_analysis')!;
      expect(r.userKeyOverride).toBe(false);
    });

    it('draft_pr does not allow user key override', () => {
      const r = DEFAULT_ROUTES.find((r) => r.id === 'draft_pr')!;
      expect(r.userKeyOverride).toBe(false);
    });

    it('vps_chat has a max of 8 000 tokens', () => {
      const r = DEFAULT_ROUTES.find((r) => r.id === 'vps_chat')!;
      expect(r.maxTokensPerRequest).toBe(8_000);
    });
  });

  describe('getDefaultRoute', () => {
    it('returns the matching route for a known id', () => {
      const r = getDefaultRoute('chat_standard');
      expect(r).toBeDefined();
      expect(r!.id).toBe('chat_standard');
    });

    it('returns undefined for an unknown id', () => {
      expect(getDefaultRoute('not_a_route')).toBeUndefined();
    });
  });

  describe('ROUTE_TO_COST_ID', () => {
    it('maps all 5 routes to a cost id', () => {
      expect(ROUTE_TO_COST_ID['chat_standard']).toBe('gemini-2.0-flash');
      expect(ROUTE_TO_COST_ID['chat_pro']).toBe('gemini-2.5-pro');
      expect(ROUTE_TO_COST_ID['repo_analysis']).toBe('gemini-2.5-flash');
      expect(ROUTE_TO_COST_ID['draft_pr']).toBe('gemini-2.5-pro');
      expect(ROUTE_TO_COST_ID['vps_chat']).toBe('gemini-2.0-flash');
    });
  });
});
