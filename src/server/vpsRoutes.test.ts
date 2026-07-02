/**
 * vpsRoutes.test.ts — Unit tests for VPS route handlers
 *
 * Validates fail-closed behavior (Issue #476):
 * - VPS_BACKEND_ENABLED === false means all routes return 503
 * - No sessionId is created without a real SSH connection
 * - exec and tree require a real backend
 *
 * When real SSH2 backend is implemented, set VPS_BACKEND_ENABLED = true
 * and add integration tests that verify actual SSH behavior.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleVpsConnect, handleVpsExec, handleVpsTree, handleVpsDisconnect } from './vpsRoutes';

function createMockRes() {
  return {
    status: vi.fn().mockReturnThis(),
    json: vi.fn().mockReturnThis(),
  };
}

describe('VPS Routes — Fail-Closed Behavior', () => {
  describe('handleVpsConnect', () => {
    it('returns 503 when backend is disabled (VPS_BACKEND_ENABLED=false)', async () => {
      const res = createMockRes();
      const req = {
        body: {
          host: 'example.com',
          port: 22,
          username: 'root',
          authMethod: 'password',
          password: 'secret',
        },
        query: {},
      };

      await handleVpsConnect(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(503);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'VPS-Backend nicht verfügbar',
          code: 'VPS_BACKEND_DISABLED',
        })
      );
    });

    it('returns 400 for missing host', async () => {
      const res = createMockRes();
      const req = {
        body: {
          host: '',
          username: 'root',
          authMethod: 'password',
          password: 'secret',
        },
        query: {},
      };

      await handleVpsConnect(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({ error: 'host und username sind Pflichtfelder' })
      );
    });

    it('returns 400 for missing password with password auth', async () => {
      const res = createMockRes();
      const req = {
        body: {
          host: 'example.com',
          username: 'root',
          authMethod: 'password',
          password: '',
        },
        query: {},
      };

      await handleVpsConnect(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({ error: 'Passwort fehlt' })
      );
    });

    it('returns 400 for missing privateKey with key auth', async () => {
      const res = createMockRes();
      const req = {
        body: {
          host: 'example.com',
          username: 'root',
          authMethod: 'key',
          privateKey: '',
        },
        query: {},
      };

      await handleVpsConnect(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({ error: 'SSH-Key fehlt' })
      );
    });
  });

  describe('handleVpsExec', () => {
    it('returns 503 when backend is disabled', async () => {
      const res = createMockRes();
      const req = {
        body: { sessionId: 'fake-session-id', command: 'ls -la' },
        query: {},
      };

      await handleVpsExec(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(503);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'VPS-Backend nicht verfügbar',
          code: 'VPS_BACKEND_DISABLED',
        })
      );
    });

    it('does NOT check for session existence when backend disabled', async () => {
      const res = createMockRes();
      const req = {
        body: { sessionId: 'any-session-id', command: 'echo test' },
        query: {},
      };

      await handleVpsExec(req as never, res as never);

      // Should fail at backend-check, not at session-check
      expect(res.status).toHaveBeenCalledWith(503);
      // If it checked session first, it would return 404 instead of 503
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'VPS_BACKEND_DISABLED' })
      );
    });
  });

  describe('handleVpsTree', () => {
    it('returns 503 when backend is disabled', async () => {
      const res = createMockRes();
      const req = {
        body: {},
        query: { sessionId: 'fake-session-id', path: '/' },
      };

      await handleVpsTree(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(503);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'VPS-Backend nicht verfügbar',
          code: 'VPS_BACKEND_DISABLED',
        })
      );
    });
  });

  describe('handleVpsDisconnect', () => {
    it('still works for cleanup even when backend disabled (no fake state)', async () => {
      const res = createMockRes();
      const req = {
        body: { sessionId: 'any-session-id' },
        query: {},
      };

      await handleVpsDisconnect(req as never, res as never);

      // Disconnect is safe - it cleans up if session exists, does nothing if not
      expect(res.json).toHaveBeenCalledWith({ ok: true });
    });
  });
});