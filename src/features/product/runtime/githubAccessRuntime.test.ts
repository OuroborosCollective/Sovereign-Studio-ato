import { describe, expect, it } from 'vitest';
import {
  maskGitHubToken,
  validateGitHubTokenFormat,
  createGitHubAccessSnapshot,
  requestGitHubAccess,
  startGitHubAccessValidation,
  completeGitHubAccessValidation,
  failGitHubAccessValidation,
  resetGitHubAccess,
  canPerformGitHubWrite,
  requiresUserAction,
  getGitHubAccessLabel,
  getGitHubAccessInstruction,
  type GitHubAccessSnapshot,
} from './githubAccessRuntime';

describe('GitHub Access Runtime', () => {
  describe('maskGitHubToken', () => {
    it('masks 40-char classic PAT correctly', () => {
      // Classic PAT: 40 random chars
      const token = 'abcdefghijklmnopqrstuvwxyz1234567890';
      expect(maskGitHubToken(token)).toBe('abcd****7890');
    });

    it('masks ghp_ fine-grained PAT correctly', () => {
      const token = 'ghp_abcdefghijklmnopqrstuvwxyz123456789ABC';
      // Token is 45 chars, shows first 4 + **** + last 4 = 9ABC
      expect(maskGitHubToken(token)).toBe('ghp_****9ABC');
    });

    it('masks short tokens as ****', () => {
      expect(maskGitHubToken('short')).toBe('****');
    });

    it('handles empty string', () => {
      expect(maskGitHubToken('')).toBe('****');
    });
  });

  describe('validateGitHubTokenFormat', () => {
    it('accepts classic 40-char PAT', () => {
      const result = validateGitHubTokenFormat('a'.repeat(40));
      expect(result.isValid).toBe(true);
    });

    it('accepts ghp_ fine-grained token', () => {
      const result = validateGitHubTokenFormat('ghp_abcdefghijklmnopqrstuvwxyz1234567890');
      expect(result.isValid).toBe(true);
    });

    it('accepts gho_ fine-grained token', () => {
      const result = validateGitHubTokenFormat('gho_abcdefghijklmnopqrstuvwxyz1234567890');
      expect(result.isValid).toBe(true);
    });

    it('accepts ghs_ fine-grained token', () => {
      const result = validateGitHubTokenFormat('ghs_abcdefghijklmnopqrstuvwxyz1234567890');
      expect(result.isValid).toBe(true);
    });

    it('rejects empty token', () => {
      const result = validateGitHubTokenFormat('');
      expect(result.isValid).toBe(false);
      expect(result.error).toContain('leer');
    });

    it('rejects token too short', () => {
      const result = validateGitHubTokenFormat('abc');
      expect(result.isValid).toBe(false);
    });

    it('rejects invalid format', () => {
      const result = validateGitHubTokenFormat('not-a-valid-token-format');
      expect(result.isValid).toBe(false);
      expect(result.error).toContain('Ungültiges Token-Format');
    });
  });

  describe('state transitions', () => {
    it('creates initial snapshot with missing state', () => {
      const snapshot = createGitHubAccessSnapshot();
      expect(snapshot.state).toBe('missing');
      expect(snapshot.maskedToken).toBeNull();
    });

    it('transitions to requested state', () => {
      const snapshot = requestGitHubAccess();
      expect(snapshot.state).toBe('requested');
    });

    it('transitions to validating state with masked token', () => {
      const snapshot = startGitHubAccessValidation('ghp_testtoken123456789012345678901234');
      expect(snapshot.state).toBe('validating');
      expect(snapshot.maskedToken).toBeTruthy();
      expect(snapshot.lastValidatedToken).toBe('ghp_testtoken123456789012345678901234');
    });

    it('transitions to ready state after validation', () => {
      const snapshot = completeGitHubAccessValidation('ghp_testtoken123456789012345678901234');
      expect(snapshot.state).toBe('ready');
      expect(snapshot.validatedAt).toBeTruthy();
      expect(snapshot.errorMessage).toBeNull();
    });

    it('transitions to invalid state with error', () => {
      const snapshot = failGitHubAccessValidation('ghp_invalid', 'Token abgelaufen');
      expect(snapshot.state).toBe('invalid');
      expect(snapshot.errorMessage).toBe('Token abgelaufen');
    });

    it('resets to initial state', () => {
      const snapshot = resetGitHubAccess();
      expect(snapshot.state).toBe('missing');
      expect(snapshot.maskedToken).toBeNull();
    });
  });

  describe('permissions', () => {
    it('allows write when ready', () => {
      const snapshot = completeGitHubAccessValidation('ghp_test') as GitHubAccessSnapshot;
      expect(canPerformGitHubWrite(snapshot)).toBe(true);
    });

    it('blocks write when missing', () => {
      const snapshot = createGitHubAccessSnapshot();
      expect(canPerformGitHubWrite(snapshot)).toBe(false);
    });

    it('blocks write when validating', () => {
      const snapshot = startGitHubAccessValidation('ghp_test') as GitHubAccessSnapshot;
      expect(canPerformGitHubWrite(snapshot)).toBe(false);
    });

    it('blocks write when invalid', () => {
      const snapshot = failGitHubAccessValidation('ghp_invalid', 'error') as GitHubAccessSnapshot;
      expect(canPerformGitHubWrite(snapshot)).toBe(false);
    });
  });

  describe('user action requirements', () => {
    it('requires action when missing', () => {
      expect(requiresUserAction(createGitHubAccessSnapshot())).toBe(true);
    });

    it('requires action when invalid', () => {
      const snapshot = failGitHubAccessValidation('ghp_invalid', 'error');
      expect(requiresUserAction(snapshot)).toBe(true);
    });

    it('does not require action when ready', () => {
      const snapshot = completeGitHubAccessValidation('ghp_valid');
      expect(requiresUserAction(snapshot)).toBe(false);
    });
  });

  describe('labels', () => {
    it('returns correct label for each state', () => {
      expect(getGitHubAccessLabel(createGitHubAccessSnapshot())).toContain('fehlt');
      expect(getGitHubAccessLabel(requestGitHubAccess())).toContain('angefordert');
      expect(getGitHubAccessLabel(startGitHubAccessValidation('test') as GitHubAccessSnapshot)).toContain('wird geprüft');
      expect(getGitHubAccessLabel(completeGitHubAccessValidation('test') as GitHubAccessSnapshot)).toContain('bereit');
      expect(getGitHubAccessLabel(failGitHubAccessValidation('test', 'err') as GitHubAccessSnapshot)).toContain('ungültig');
    });
  });

  describe('instructions', () => {
    it('shows instruction for missing state', () => {
      const instruction = getGitHubAccessInstruction(createGitHubAccessSnapshot());
      expect(instruction).toContain('benötigt');
    });

    it('shows error message for invalid state', () => {
      const snapshot = failGitHubAccessValidation('ghp_invalid', 'Token abgelaufen');
      const instruction = getGitHubAccessInstruction(snapshot);
      expect(instruction).toContain('Token abgelaufen');
    });
  });
});
