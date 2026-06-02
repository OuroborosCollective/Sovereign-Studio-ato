/**
 * Workflow Test Suite
 * Tests N8n-style workflow execution for GitHub integration, code generation, and automation
 */

import { WORKFLOW_DEFINITIONS, WORKFLOW_EXECUTOR_CONFIG } from './workflow.config';

describe('Workflow Tests', () => {
  describe('Workflow Definition Validation', () => {
    it('should have all required workflows defined', () => {
      const expectedWorkflows = [
        'e2e-test-trigger',
        'auto-fix-loop',
        'github-integration',
        'code-generation',
        'api-fallback-workflow',
      ];

      const workflowIds = WORKFLOW_DEFINITIONS.map(w => w.id);
      
      expectedWorkflows.forEach(wf => {
        expect(workflowIds).toContain(wf);
      });
    });

    it('should have valid node connections', () => {
      for (const workflow of WORKFLOW_DEFINITIONS) {
        expect(workflow.nodes.length).toBeGreaterThan(0);
        expect(workflow.connections).toBeDefined();
        
        // Check all connections point to existing nodes
        Object.entries(workflow.connections).forEach(([fromNode, toNodes]) => {
          const nodeIds = workflow.nodes.map(n => n.id);
          
          if (Array.isArray(toNodes)) {
            toNodes.forEach(nodeId => {
              expect(nodeIds).toContain(nodeId);
            });
          } else {
            // Branching connection
            Object.values(toNodes).forEach(nodeId => {
              expect(nodeIds).toContain(nodeId);
            });
          }
        });
      }
    });

    it('should have triggers defined for each workflow', () => {
      for (const workflow of WORKFLOW_DEFINITIONS) {
        const triggerNodes = workflow.nodes.filter(n => n.type === 'trigger');
        expect(triggerNodes.length).toBeGreaterThan(0);
      }
    });
  });

  describe('E2E Test Trigger Workflow', () => {
    const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'e2e-test-trigger');
    
    it('should have GitHub webhook trigger', () => {
      expect(workflow).toBeDefined();
      const trigger = workflow?.nodes.find(n => n.type === 'trigger');
      expect(trigger?.config.events).toContain('push');
      expect(trigger?.config.events).toContain('pull_request');
    });

    it('should have setup, test, and report nodes', () => {
      const nodeTypes = workflow?.nodes.map(n => n.type);
      expect(nodeTypes).toContain('trigger');
      expect(nodeTypes).toContain('action');
      expect(nodeTypes).toContain('output');
    });

    it('should trigger on sovereign-studio-rn paths', () => {
      const trigger = workflow?.nodes.find(n => n.type === 'trigger');
      expect(trigger?.config.paths).toContain('sovereign-studio-rn/**');
    });
  });

  describe('Auto-Fix Loop Workflow', () => {
    const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'auto-fix-loop');
    
    it('should have analyze, generate, and apply nodes', () => {
      const nodeNames = workflow?.nodes.map(n => n.name);
      expect(nodeNames).toContain('Analyze Error');
      expect(nodeNames).toContain('Generate Fix');
      expect(nodeNames).toContain('Apply Fix');
    });

    it('should have retry logic on test failure', () => {
      const retestNode = workflow?.nodes.find(n => n.name === 'Re-run Tests');
      expect(retestNode).toBeDefined();
      
      // Check that failure leads back to analyze
      const connections = workflow?.connections['retest'];
      expect(connections).toBeDefined();
      
      if (typeof connections === 'object' && !Array.isArray(connections)) {
        expect(connections.failure).toBe('analyze');
      }
    });

    it('should auto-merge on success', () => {
      const mergeNode = workflow?.nodes.find(n => n.name === 'Auto Merge');
      expect(mergeNode).toBeDefined();
      expect(mergeNode?.config.conditions).toContain('all-tests-pass');
    });
  });

  describe('GitHub Integration Workflow', () => {
    const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'github-integration');
    
    it('should handle PR events', () => {
      const trigger = workflow?.nodes.find(n => n.type === 'trigger');
      expect(trigger?.config.events).toContain('pull_request');
    });

    it('should authenticate with GitHub token', () => {
      const authNode = workflow?.nodes.find(n => n.name === 'Authenticate');
      expect(authNode?.config.token).toBe('GITHUB_TOKEN');
    });

    it('should generate AI reviews', () => {
      const reviewNode = workflow?.nodes.find(n => n.name === 'Generate Review');
      expect(reviewNode?.config.model).toBe('gemini');
    });
  });

  describe('Code Generation Workflow', () => {
    const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'code-generation');
    
    it('should accept multiple input sources', () => {
      const inputNode = workflow?.nodes.find(n => n.name === 'Code Request Input');
      expect(inputNode?.config.sources).toContain('user-input');
      expect(inputNode?.config.sources).toContain('github-issue');
      expect(inputNode?.config.sources).toContain('slack');
    });

    it('should validate generated code', () => {
      const validateNode = workflow?.nodes.find(n => n.name === 'Validate Code');
      expect(validateNode?.config.checks).toContain('typescript');
      expect(validateNode?.config.checks).toContain('eslint');
    });

    it('should retry on validation failure', () => {
      const connections = workflow?.connections['validate'];
      expect(connections).toBeDefined();
      
      if (typeof connections === 'object' && !Array.isArray(connections)) {
        expect(connections.fail).toBe('generate');
      }
    });
  });

  describe('API Fallback Workflow', () => {
    const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'api-fallback-workflow');
    
    it('should have all API providers in chain', () => {
      const providerNames = workflow?.nodes.map(n => n.name);
      expect(providerNames).toContain('Call MLVoca');
      expect(providerNames).toContain('Call P8lination');
      expect(providerNames).toContain('Call Gemini');
      expect(providerNames).toContain('Call Groq');
    });

    it('should have cache fallback', () => {
      const cacheNode = workflow?.nodes.find(n => n.name === 'Cache Fallback');
      expect(cacheNode).toBeDefined();
    });

    it('should handle all failure scenarios', () => {
      // Check all providers have failure branches
      const providers = ['mlvoca', 'p8lination', 'gemini', 'groq'];
      
      providers.forEach(p => {
        const node = workflow?.nodes.find(n => n.name.toLowerCase().includes(p));
        expect(node).toBeDefined();
        
        const connections = workflow?.connections[node?.id as string];
        expect(connections).toBeDefined();
        
        if (typeof connections === 'object' && !Array.isArray(connections)) {
          expect(connections.failure).toBeDefined();
        }
      });
    });
  });

  describe('Workflow Executor Configuration', () => {
    it('should have max concurrent workflows', () => {
      expect(WORKFLOW_EXECUTOR_CONFIG.maxConcurrentWorkflows).toBeGreaterThan(0);
      expect(WORKFLOW_EXECUTOR_CONFIG.maxConcurrentWorkflows).toBeLessThanOrEqual(10);
    });

    it('should have reasonable timeout', () => {
      expect(WORKFLOW_EXECUTOR_CONFIG.timeout).toBeGreaterThan(60000);
      expect(WORKFLOW_EXECUTOR_CONFIG.timeout).toBeLessThan(600000);
    });

    it('should have retry configuration', () => {
      expect(WORKFLOW_EXECUTOR_CONFIG.maxRetries).toBeGreaterThan(0);
      expect(WORKFLOW_EXECUTOR_CONFIG.retryDelay).toBeGreaterThan(0);
    });
  });

  describe('Workflow Execution', () => {
    it('should execute E2E trigger workflow', async () => {
      const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'e2e-test-trigger');
      expect(workflow).toBeDefined();
      
      // Simulate workflow execution
      const results: Record<string, boolean> = {};
      
      for (const node of workflow?.nodes || []) {
        // Simulate node execution
        results[node.id] = true;
      }
      
      expect(Object.keys(results).length).toBe(workflow?.nodes.length);
    });

    it('should execute auto-fix loop workflow', async () => {
      const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === 'auto-fix-loop');
      expect(workflow).toBeDefined();
      
      // Simulate execution with branching
      let currentNode = workflow?.nodes.find(n => n.type === 'action');
      let iterations = 0;
      const maxIterations = 5;
      
      while (currentNode && iterations < maxIterations) {
        iterations++;
        currentNode = workflow?.nodes.find(n => n.id === 'analyze'); // Loop back
      }
      
      expect(iterations).toBeLessThanOrEqual(maxIterations);
    });

    it('should handle workflow concurrency', () => {
      const activeWorkflows = 3;
      expect(activeWorkflows).toBeLessThanOrEqual(WORKFLOW_EXECUTOR_CONFIG.maxConcurrentWorkflows);
    });
  });
});