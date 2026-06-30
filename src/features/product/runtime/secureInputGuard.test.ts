import { describe, it, expect } from 'vitest';
import { scanForSecret, redactSecret, evaluateInputPolicy } from './secureInputGuard';

describe('secureInputGuard', () => {
  describe('scanForSecret', () => {
    it('returns detected=false for normal chat messages', () => {
      expect(scanForSecret('Baue mir ein React-Formular').detected).toBe(false);
      expect(scanForSecret('Wie funktioniert OAuth?').detected).toBe(false);
      expect(scanForSecret('').detected).toBe(false);
    });

    it('detects classic GitHub PAT (ghp_)', () => {
      const input = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
      if (result.detected) {
        expect(result.kind).toBe('github_pat');
        expect(result.hint).toContain('GitHub');
      }
    });

    it('detects fine-grained GitHub PAT (github_pat_)', () => {
      const input = 'github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
      if (result.detected) {
        expect(result.kind).toBe('github_pat_fine');
      }
    });

    it('detects OpenAI key (sk-)', () => {
      const input = 'sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
      if (result.detected) {
        expect(result.kind).toBe('openai_key');
      }
    });

    it('detects Anthropic key (sk-ant-)', () => {
      const input = 'sk-ant-api-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef1234';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
      if (result.detected) {
        expect(result.kind).toBe('anthropic_key');
      }
    });

    it('detects Bearer token in Authorization header context', () => {
      const input = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abc123';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
      if (result.detected) {
        expect(result.kind).toBe('generic_bearer');
      }
    });

    it('detects token=value style', () => {
      const input = 'token=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
    });

    it('detects api_key=value style', () => {
      const input = 'api_key=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
    });

    it('does not flag short strings', () => {
      expect(scanForSecret('ghp_short').detected).toBe(false);
      expect(scanForSecret('sk-abc').detected).toBe(false);
    });

    it('detects PAT embedded in longer message', () => {
      const input = 'Mein Token ist ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01 bitte speichere ihn';
      const result = scanForSecret(input);
      expect(result.detected).toBe(true);
      if (result.detected) {
        expect(result.kind).toBe('github_pat');
      }
    });
  });

  describe('redactSecret', () => {
    it('replaces PAT with [REDACTED]', () => {
      const input = 'Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01';
      const redacted = redactSecret(input);
      expect(redacted).toContain('[REDACTED]');
      expect(redacted).not.toContain('ghp_');
    });

    it('replaces multiple secrets in one string', () => {
      const input = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01 and sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabc';
      const redacted = redactSecret(input);
      expect(redacted).not.toContain('ghp_');
      expect(redacted).not.toContain('sk-');
    });

    it('leaves normal text unchanged', () => {
      expect(redactSecret('Baue mir ein Feature')).toBe('Baue mir ein Feature');
    });
  });

  describe('evaluateInputPolicy', () => {
    it('returns shouldBlock=false for safe input', () => {
      const policy = evaluateInputPolicy('Was macht diese Funktion?');
      expect(policy.shouldBlock).toBe(false);
      expect(policy.kind).toBeNull();
    });

    it('returns shouldBlock=true with message and action for PAT', () => {
      const policy = evaluateInputPolicy('ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01');
      expect(policy.shouldBlock).toBe(true);
      expect(policy.kind).toBe('github_pat');
      expect(policy.userMessage).toContain('sicheres Zugangsfeld');
      expect(policy.actionLabel).toContain('PAT');
    });

    it('user message never exposes the token value', () => {
      const token = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef01';
      const policy = evaluateInputPolicy(token);
      if (policy.shouldBlock) {
        expect(policy.userMessage).not.toContain(token);
      }
    });
  });
});
