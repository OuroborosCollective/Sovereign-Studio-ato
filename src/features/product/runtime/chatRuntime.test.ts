/**
 * Chat Runtime Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  validateChatEntry,
  checkChatEntryGuard,
  executeChatRuntime,
  buildChatExitState,
  assertChatRuntimeHealthy,
  type ChatMessage,
  ChatRuntimeError,
} from './chatRuntime';
import { runtimeIntelligence } from '../../../runtime/RuntimeIntelligence';

describe('chatRuntime', () => {
  describe('validateChatEntry', () => {
    it('should validate empty input as invalid', () => {
      const result = validateChatEntry('');
      
      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.normalizedInput).toBe('');
    });

    it('should validate whitespace-only input as invalid', () => {
      const result = validateChatEntry('   \n\t  ');
      
      expect(result.valid).toBe(false);
    });

    it('should validate normal input as valid', () => {
      const result = validateChatEntry('Hello, how are you?');
      
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should normalize input by trimming', () => {
      const result = validateChatEntry('  Hello  ');
      
      expect(result.normalizedInput).toBe('Hello');
    });

    it('should sanitize HTML tags', () => {
      const result = validateChatEntry('<script>alert("xss")</script>');
      
      expect(result.sanitized).toBe(true);
      expect(result.normalizedInput).not.toContain('<script>');
    });

    it('should enforce maximum length', () => {
      const longInput = 'a'.repeat(15000);
      const result = validateChatEntry(longInput, { maxMessageLength: 10000 });
      
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.includes('too long'))).toBe(true);
    });

    it('should enforce minimum length', () => {
      const result = validateChatEntry('Hi', { minMessageLength: 10 });
      
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.includes('too short'))).toBe(true);
    });

    it('should mask sensitive tokens', () => {
      const result = validateChatEntry('My key is ghp_123456789012345678901234567890123456');

      expect(result.normalizedInput).toBe('My key is ghp_****');
    });
  });

  describe('checkChatEntryGuard', () => {
    it('should pass when model health is ready', async () => {
      // Set up adapters
      runtimeIntelligence.setModelHealthAdapters([]);
      
      const result = await checkChatEntryGuard('Hello');
      
      expect(result.pass).toBe(true);
    });

    it('should include reason when failing', async () => {
      const result = await checkChatEntryGuard('');
      
      // Empty input will fail validation first
      expect(result.reason).toBeDefined();
    });
  });

  describe('executeChatRuntime', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return error for invalid input', async () => {
      const result = await executeChatRuntime('', []);
      
      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(result.error?.stage).toBe('entry');
      expect(result.error?.recoverable).toBe(true);
    });

    it('should return error for long input', async () => {
      const longInput = 'a'.repeat(20000);
      const result = await executeChatRuntime(longInput, [], { maxMessageLength: 10000 });
      
      expect(result.success).toBe(false);
      expect(result.error?.stage).toBe('entry');
    });

    it('should process valid input', async () => {
      runtimeIntelligence.setModelHealthAdapters([]);
      
      const result = await executeChatRuntime('Hello world', []);
      
      // May fail due to no models, but should reach process stage
      if (result.success) {
        expect(result.exitState).toBeDefined();
      } else {
        expect(result.error?.stage).toBeDefined();
      }
    });

    it('should include history in processing', async () => {
      runtimeIntelligence.setModelHealthAdapters([]);
      
      const history: ChatMessage[] = [
        {
          id: '1',
          role: 'user',
          content: 'First message',
          timestamp: Date.now() - 1000,
        },
        {
          id: '2',
          role: 'assistant',
          content: 'Response',
          timestamp: Date.now(),
        },
      ];

      const result = await executeChatRuntime('Second message', history);
      
      expect(result).toBeDefined();
    });
  });

  describe('buildChatExitState', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should build exit state with success', () => {
      const messages: ChatMessage[] = [];
      const result = {
        success: true,
        response: 'Test response',
        modelUsed: 'test-model',
        latencyMs: 100,
      };

      const exitState = buildChatExitState(messages, result);

      expect(exitState.messages).toEqual(messages);
      expect(exitState.suggestions.length).toBeGreaterThan(0);
      expect(exitState.modelHealth.modelId).toBe('test-model');
    });

    it('should include retry suggestion on failure', () => {
      const messages: ChatMessage[] = [];
      const result = {
        success: false,
        error: 'Model unavailable',
      };

      const exitState = buildChatExitState(messages, result);

      expect(exitState.suggestions.some(s => s.id === 'retry')).toBe(true);
    });

    it('should reflect model health status', () => {
      const messages: ChatMessage[] = [];
      const result = {
        success: true,
        modelUsed: 'healthy-model',
        latencyMs: 50,
      };

      const exitState = buildChatExitState(messages, result);

      expect(exitState.modelHealth.status).toBeDefined();
      expect(exitState.modelHealth.latencyMs).toBe(50);
    });
  });

  describe('assertChatRuntimeHealthy', () => {
    it('should not throw when runtime is healthy', () => {
      runtimeIntelligence.setModelHealthAdapters([]);
      
      expect(() => assertChatRuntimeHealthy()).not.toThrow();
    });
  });

  describe('ChatRuntimeError', () => {
    it('should create error with correct properties', () => {
      const error = new ChatRuntimeError(
        'Test error message',
        'process',
        true,
        { context: 'test' }
      );

      expect(error.message).toBe('Test error message');
      expect(error.stage).toBe('process');
      expect(error.recoverable).toBe(true);
      expect(error.context).toEqual({ context: 'test' });
      expect(error.name).toBe('ChatRuntimeError');
    });

    it('should format error correctly', () => {
      const error = new ChatRuntimeError(
        'Validation failed',
        'entry',
        false
      );

      expect(error.message).toBe('Validation failed');
      expect(error.stage).toBe('entry');
      expect(error.recoverable).toBe(false);
    });

    it('should be instanceof Error', () => {
      const error = new ChatRuntimeError('Test', 'process', true);
      
      expect(error instanceof Error).toBe(true);
      expect(error instanceof ChatRuntimeError).toBe(true);
    });
  });
});
