import { describe, it, expect } from 'vitest';
import type { 
  ChatMessage, 
  Suggestion, 
  ArchitectureAnalysis,
  SuggestionType,
  ChatRole,
  PipelineState,
  ProjectSettings,
  Card,
  WorkView,
  MobilePane
} from './types';

describe('Product Types - Runtime Verification', () => {
  describe('ChatMessage', () => {
    it('should have correct structure', () => {
      const message: ChatMessage = {
        id: '1',
        role: 'assistant',
        content: 'Test message',
        timestamp: Date.now(),
      };
      
      expect(message.id).toBeDefined();
      expect(message.role).toBe('assistant');
      expect(message.content).toBe('Test message');
      expect(message.timestamp).toBeGreaterThan(0);
    });

    it('should support user role', () => {
      const message: ChatMessage = {
        id: '2',
        role: 'user',
        content: 'User message',
        timestamp: Date.now(),
      };
      
      expect(message.role).toBe('user');
    });

    it('should support system role', () => {
      const message: ChatMessage = {
        id: '3',
        role: 'system',
        content: 'System message',
        timestamp: Date.now(),
      };
      
      expect(message.role).toBe('system');
    });

    it('should have valid id type', () => {
      const message: ChatMessage = {
        id: 'abc-123-xyz',
        role: 'assistant',
        content: 'Test',
        timestamp: Date.now(),
      };
      
      expect(typeof message.id).toBe('string');
    });
  });

  describe('Suggestion', () => {
    it('should have correct structure', () => {
      const suggestion: Suggestion = {
        id: 's1',
        type: 'feature',
        title: 'Test Feature',
        description: 'A test feature description',
        priority: 'high',
      };
      
      expect(suggestion.id).toBeDefined();
      expect(suggestion.type).toBe('feature');
      expect(suggestion.title).toBeDefined();
      expect(suggestion.description).toBeDefined();
      expect(suggestion.priority).toBe('high');
    });

    it('should support accepted optional property', () => {
      const suggestion: Suggestion = {
        id: 's2',
        type: 'error',
        title: 'Warning',
        description: 'A warning description',
        priority: 'medium',
        accepted: true,
      };
      
      expect(suggestion.accepted).toBe(true);
    });

    it('should support all suggestion types', () => {
      const types: SuggestionType[] = ['feature', 'error', 'improvement'];
      
      types.forEach(type => {
        const suggestion: Suggestion = {
          id: `s-${type}`,
          type,
          title: `Test ${type}`,
          description: 'Description',
          priority: 'low',
        };
        
        expect(suggestion.type).toBe(type);
      });
    });

    it('should support all priority levels', () => {
      const priorities: Suggestion['priority'][] = ['high', 'medium', 'low'];
      
      priorities.forEach(priority => {
        const suggestion: Suggestion = {
          id: `s-${priority}`,
          type: 'feature',
          title: `Test ${priority}`,
          description: 'Description',
          priority,
        };
        
        expect(suggestion.priority).toBe(priority);
      });
    });
  });

  describe('ArchitectureAnalysis', () => {
    it('should have correct structure', () => {
      const analysis: ArchitectureAnalysis = {
        summary: 'Test summary',
        components: ['Component1', 'Component2'],
        potentialIssues: ['Issue1'],
        suggestedFeatures: ['Feature1'],
        integrations: ['Integration1'],
      };
      
      expect(analysis.summary).toBeDefined();
      expect(Array.isArray(analysis.components)).toBe(true);
      expect(Array.isArray(analysis.potentialIssues)).toBe(true);
      expect(Array.isArray(analysis.suggestedFeatures)).toBe(true);
      expect(Array.isArray(analysis.integrations)).toBe(true);
    });

    it('should allow empty arrays', () => {
      const analysis: ArchitectureAnalysis = {
        summary: 'Empty analysis',
        components: [],
        potentialIssues: [],
        suggestedFeatures: [],
        integrations: [],
      };
      
      expect(analysis.components.length).toBe(0);
      expect(analysis.potentialIssues.length).toBe(0);
    });

    it('should allow mixed content in arrays', () => {
      const analysis: ArchitectureAnalysis = {
        summary: 'Mixed analysis',
        components: ['Backend', 'Frontend'],
        potentialIssues: ['Missing tests', 'Security concern'],
        suggestedFeatures: ['Dark mode', 'Notifications'],
        integrations: ['Stripe', 'GitHub'],
      };
      
      expect(analysis.components.length).toBe(2);
      expect(analysis.potentialIssues.length).toBe(2);
      expect(analysis.suggestedFeatures.length).toBe(2);
      expect(analysis.integrations.length).toBe(2);
    });
  });

  describe('PipelineState', () => {
    it('should support all valid states', () => {
      const states: PipelineState[] = [
        'idle',
        'planning',
        'generating',
        'validating',
        'failed',
        'fixing',
        'revalidating',
        'green',
        'blocked'
      ];
      
      states.forEach(state => {
        expect(typeof state).toBe('string');
      });
    });
  });

  describe('ProjectSettings', () => {
    it('should have correct structure', () => {
      const settings: ProjectSettings = {
        repoMode: 'single',
        packageManager: 'npm',
        installStrategy: 'safe',
        linter: 'eslint',
        specialization: 'web',
        maxFixLoops: 3,
      };
      
      expect(settings.repoMode).toBe('single');
      expect(settings.packageManager).toBe('npm');
      expect(settings.installStrategy).toBe('safe');
      expect(settings.linter).toBe('eslint');
      expect(settings.specialization).toBe('web');
      expect(settings.maxFixLoops).toBe(3);
    });

    it('should support monorepo mode', () => {
      const settings: ProjectSettings = {
        repoMode: 'monorepo',
        packageManager: 'pnpm',
        installStrategy: 'workspace',
        linter: 'biome',
        specialization: 'fullstack',
        maxFixLoops: 5,
      };
      
      expect(settings.repoMode).toBe('monorepo');
      expect(settings.packageManager).toBe('pnpm');
    });

    it('should support optional workMode', () => {
      const settings: ProjectSettings = {
        repoMode: 'single',
        packageManager: 'npm',
        installStrategy: 'safe',
        linter: 'eslint',
        specialization: 'web',
        maxFixLoops: 3,
        workMode: 'autonomous',
      };
      
      expect(settings.workMode).toBe('autonomous');
    });
  });

  describe('Card', () => {
    it('should have correct structure', () => {
      const card: Card = {
        id: 'card-1',
        title: 'Task Title',
        body: 'Task description',
      };
      
      expect(card.id).toBeDefined();
      expect(card.title).toBeDefined();
      expect(card.body).toBeDefined();
    });

    it('should allow long content', () => {
      const card: Card = {
        id: 'card-long',
        title: 'A'.repeat(100),
        body: 'B'.repeat(500),
      };
      
      expect(card.title.length).toBe(100);
      expect(card.body.length).toBe(500);
    });
  });

  describe('WorkView', () => {
    it('should support editor view', () => {
      const view: WorkView = 'editor';
      expect(view).toBe('editor');
    });

    it('should support pipeline view', () => {
      const view: WorkView = 'pipeline';
      expect(view).toBe('pipeline');
    });
  });

  describe('MobilePane', () => {
    it('should support auftrag pane', () => {
      const pane: MobilePane = 'auftrag';
      expect(pane).toBe('auftrag');
    });

    it('should support live pane', () => {
      const pane: MobilePane = 'live';
      expect(pane).toBe('live');
    });

    it('should support log pane', () => {
      const pane: MobilePane = 'log';
      expect(pane).toBe('log');
    });
  });

  describe('ChatRole', () => {
    it('should support user role', () => {
      const role: ChatRole = 'user';
      expect(role).toBe('user');
    });

    it('should support assistant role', () => {
      const role: ChatRole = 'assistant';
      expect(role).toBe('assistant');
    });

    it('should support system role', () => {
      const role: ChatRole = 'system';
      expect(role).toBe('system');
    });
  });

  describe('Type Compatibility', () => {
    it('should be compatible with JSON serialization', () => {
      const message: ChatMessage = {
        id: '1',
        role: 'assistant',
        content: 'Test',
        timestamp: 1234567890,
      };
      
      const json = JSON.stringify(message);
      const parsed = JSON.parse(json) as ChatMessage;
      
      expect(parsed.id).toBe(message.id);
      expect(parsed.role).toBe(message.role);
      expect(parsed.content).toBe(message.content);
    });

    it('should be compatible with API responses', () => {
      const suggestion: Suggestion = {
        id: '1',
        type: 'feature',
        title: 'Test',
        description: 'Description',
        priority: 'high',
      };
      
      const apiResponse = {
        ...suggestion,
        metadata: { created: Date.now() },
      };
      
      expect(apiResponse.type).toBe('feature');
    });
  });

  describe('Edge Cases', () => {
    it('should handle unicode in messages', () => {
      const message: ChatMessage = {
        id: '1',
        role: 'assistant',
        content: 'Willkommen! 你好 🚀',
        timestamp: Date.now(),
      };
      
      expect(message.content).toContain('Willkommen');
    });

    it('should handle empty strings', () => {
      const suggestion: Suggestion = {
        id: 'empty',
        type: 'feature',
        title: '',
        description: '',
        priority: 'low',
      };
      
      expect(suggestion.title).toBe('');
      expect(suggestion.description).toBe('');
    });

    it('should handle special characters in analysis', () => {
      const analysis: ArchitectureAnalysis = {
        summary: 'Test with <script>alert("xss")</script>',
        components: ['API: /v1/users?format=json'],
        potentialIssues: ['Error: "File not found" at line 42'],
        suggestedFeatures: ['Feature with "quotes" and \'apostrophes\''],
        integrations: ['REST API (https://api.example.com)'],
      };
      
      expect(analysis.summary).toContain('<script>');
      expect(analysis.components[0]).toContain('/v1/users');
    });

    it('should handle negative timestamps', () => {
      const message: ChatMessage = {
        id: '1',
        role: 'assistant',
        content: 'Test',
        timestamp: -1,
      };
      
      expect(message.timestamp).toBe(-1);
    });
  });
});
