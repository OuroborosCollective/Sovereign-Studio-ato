import { describe, it, expect } from 'vitest';
import {
  calculateCredits,
  creditsToEur,
  getCostEntry,
  COST_CONFIG,
  EUR_PER_CREDIT,
} from './costConfig';

describe('costConfig', () => {
  describe('calculateCredits — LLM calls', () => {
    it('charges 1 credit per 1 000 tokens for gemini-2.0-flash', () => {
      expect(calculateCredits('gemini-2.0-flash', 1000)).toBe(1);
      expect(calculateCredits('gemini-2.0-flash', 5000)).toBe(5);
      expect(calculateCredits('gemini-2.0-flash', 500)).toBe(1); // ceil
    });

    it('charges 8 credits per 1 000 tokens for gemini-2.5-pro', () => {
      expect(calculateCredits('gemini-2.5-pro', 1000)).toBe(8);
      expect(calculateCredits('gemini-2.5-pro', 2000)).toBe(16);
      expect(calculateCredits('gemini-2.5-pro', 100)).toBe(1); // ceil(0.8) = 1
    });

    it('charges 2 credits per 1 000 tokens for gemini-2.5-flash', () => {
      expect(calculateCredits('gemini-2.5-flash', 1000)).toBe(2);
      expect(calculateCredits('gemini-2.5-flash', 500)).toBe(1); // ceil(1) = 1
    });

    it('uses ceil so partial token blocks are never undercharged', () => {
      expect(calculateCredits('gemini-2.0-flash', 1)).toBe(1);
      expect(calculateCredits('gemini-2.0-flash', 999)).toBe(1);
      expect(calculateCredits('gemini-2.0-flash', 1001)).toBe(2);
    });

    it('defaults tokenCount to 0 when omitted → 0 credits', () => {
      expect(calculateCredits('gemini-2.0-flash')).toBe(0);
    });
  });

  describe('calculateCredits — flat tool/API costs', () => {
    it('charges 5 credits flat for tool_vps_exec regardless of tokenCount', () => {
      expect(calculateCredits('tool_vps_exec', 0)).toBe(5);
      expect(calculateCredits('tool_vps_exec', 99_999)).toBe(5);
    });

    it('charges 10 credits flat for tool_github_pr', () => {
      expect(calculateCredits('tool_github_pr')).toBe(10);
    });

    it('charges 3 credits flat for tool_repo_load', () => {
      expect(calculateCredits('tool_repo_load')).toBe(3);
    });
  });

  describe('calculateCredits — unknown id', () => {
    it('returns 0 for unknown cost ids', () => {
      expect(calculateCredits('unknown_model', 1000)).toBe(0);
      expect(calculateCredits('')).toBe(0);
    });
  });

  describe('creditsToEur', () => {
    it('converts 1 credit to €0.0001', () => {
      expect(creditsToEur(1)).toBe('0.0001');
    });

    it('converts 10 000 credits to €1.0000', () => {
      expect(creditsToEur(10_000)).toBe('1.0000');
    });

    it('converts 0 credits to €0.0000', () => {
      expect(creditsToEur(0)).toBe('0.0000');
    });
  });

  describe('EUR_PER_CREDIT', () => {
    it('equals 0.0001', () => {
      expect(EUR_PER_CREDIT).toBe(0.0001);
    });
  });

  describe('getCostEntry', () => {
    it('returns the entry for a known id', () => {
      const entry = getCostEntry('gemini-2.0-flash');
      expect(entry).toBeDefined();
      expect(entry!.creditsPerUnit).toBe(1);
    });

    it('returns undefined for an unknown id', () => {
      expect(getCostEntry('does-not-exist')).toBeUndefined();
    });
  });

  describe('COST_CONFIG completeness', () => {
    it('contains all required LLM models', () => {
      const ids = COST_CONFIG.map((e) => e.id);
      expect(ids).toContain('gemini-2.0-flash');
      expect(ids).toContain('gemini-2.5-pro');
      expect(ids).toContain('gemini-2.5-flash');
    });

    it('contains all tool entries', () => {
      const ids = COST_CONFIG.map((e) => e.id);
      expect(ids).toContain('tool_vps_exec');
      expect(ids).toContain('tool_github_pr');
      expect(ids).toContain('tool_repo_load');
    });
  });
});
