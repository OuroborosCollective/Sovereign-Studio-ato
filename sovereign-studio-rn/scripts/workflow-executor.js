#!/usr/bin/env node
/**
 * N8n-style Workflow Executor
 * Executes workflows defined in workflow.config.ts
 */

import { WORKFLOW_DEFINITIONS, WORKFLOW_EXECUTOR_CONFIG } from '../e2e/workflows/workflow.config';

interface WorkflowResult {
  workflowId: string;
  success: boolean;
  nodeResults: Record<string, {
    success: boolean;
    output?: unknown;
    error?: string;
    duration: number;
  }>;
  totalDuration: number;
}

class WorkflowExecutor {
  private runningWorkflows: Set<string> = new Set();

  async executeWorkflow(workflowId: string): Promise<WorkflowResult> {
    const workflow = WORKFLOW_DEFINITIONS.find(w => w.id === workflowId);
    
    if (!workflow) {
      throw new Error(`Workflow not found: ${workflowId}`);
    }

    if (this.runningWorkflows.has(workflowId)) {
      throw new Error(`Workflow already running: ${workflowId}`);
    }

    if (!workflow.enabled) {
      throw new Error(`Workflow disabled: ${workflowId}`);
    }

    this.runningWorkflows.add(workflowId);
    const startTime = Date.now();
    
    console.log(`\n🚀 Executing workflow: ${workflow.name}`);
    console.log(`   Description: ${workflow.description}`);
    console.log('='.repeat(50));

    const nodeResults: Record<string, {
      success: boolean;
      output?: unknown;
      error?: string;
      duration: number;
    }> = {};

    try {
      // Start from trigger nodes
      const triggerNodes = workflow.nodes.filter(n => n.type === 'trigger');
      
      for (const trigger of triggerNodes) {
        const result = await this.executeNode(workflow, trigger.id, nodeResults);
        nodeResults[trigger.id] = result;
      }

      // Continue execution from triggered nodes
      for (const trigger of triggerNodes) {
        await this.executeNextNodes(workflow, trigger.id, nodeResults);
      }

    } finally {
      this.runningWorkflows.delete(workflowId);
    }

    const totalDuration = Date.now() - startTime;
    const success = Object.values(nodeResults).every(r => r.success);

    console.log('\n' + '='.repeat(50));
    console.log(`✅ Workflow completed: ${workflow.name}`);
    console.log(`   Duration: ${totalDuration}ms`);
    console.log(`   Status: ${success ? 'SUCCESS' : 'FAILED'}`);

    return {
      workflowId,
      success,
      nodeResults,
      totalDuration,
    };
  }

  private async executeNextNodes(
    workflow: typeof WORKFLOW_DEFINITIONS[0],
    currentNodeId: string,
    nodeResults: Record<string, unknown>
  ): Promise<void> {
    const connections = workflow.connections[currentNodeId];
    
    if (!connections) return;

    if (Array.isArray(connections)) {
      // Sequential execution
      for (const nextNodeId of connections) {
        await this.executeNextNodes(workflow, nextNodeId, nodeResults as Record<string, {
          success: boolean;
          output?: unknown;
          error?: string;
          duration: number;
        }>);
      }
    } else {
      // Conditional branching - execute all branches
      for (const [, nextNodeId] of Object.entries(connections)) {
        await this.executeNextNodes(workflow, nextNodeId, nodeResults as Record<string, {
          success: boolean;
          output?: unknown;
          error?: string;
          duration: number;
        }>);
      }
    }
  }

  private async executeNode(
    workflow: typeof WORKFLOW_DEFINITIONS[0],
    nodeId: string,
    nodeResults: Record<string, {
      success: boolean;
      output?: unknown;
      error?: string;
      duration: number;
    }>
  ): Promise<{ success: boolean; output?: unknown; error?: string; duration: number }> {
    const node = workflow.nodes.find(n => n.id === nodeId);
    
    if (!node) {
      return { success: false, error: 'Node not found', duration: 0 };
    }

    console.log(`📋 Executing node: ${node.name} (${node.type})`);

    const startTime = Date.now();
    
    try {
      // Simulate node execution based on type
      const output = await this.executeNodeAction(node);
      const duration = Date.now() - startTime;

      const result = { success: true, output, duration };
      nodeResults[nodeId] = result;

      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : String(error);

      console.log(`   ❌ Failed: ${errorMessage}`);

      const result = { success: false, error: errorMessage, duration };
      nodeResults[nodeId] = result;

      return result;
    }
  }

  private async executeNodeAction(node: { type: string; name: string; config: Record<string, unknown> }): Promise<unknown> {
    // Simulate different node types
    switch (node.type) {
      case 'trigger':
        console.log(`   🔔 Trigger: ${JSON.stringify(node.config)}`);
        return { triggered: true, config: node.config };

      case 'action':
        console.log(`   ⚙️  Action: ${node.config.action || node.name}`);
        await this.delay(100); // Simulate work
        return { action: node.name, success: true };

      case 'condition':
        console.log(`   🔀 Condition: ${node.config.condition}`);
        return { condition: node.config.condition, result: true };

      case 'transform':
        console.log(`   🔄 Transform: ${node.config.parser}`);
        return { transformed: true, parser: node.config.parser };

      case 'output':
        console.log(`   📤 Output: ${node.config.format}`);
        return { output: true, format: node.config.format };

      default:
        return { nodeType: node.type };
    }
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async executeAllWorkflows(): Promise<WorkflowResult[]> {
    const results: WorkflowResult[] = [];

    for (const workflow of WORKFLOW_DEFINITIONS) {
      if (workflow.enabled) {
        try {
          const result = await this.executeWorkflow(workflow.id);
          results.push(result);
        } catch (error) {
          console.error(`Failed to execute workflow ${workflow.id}:`, error);
          results.push({
            workflowId: workflow.id,
            success: false,
            nodeResults: {},
            totalDuration: 0,
          });
        }
      }
    }

    return results;
  }
}

// CLI Interface
const executor = new WorkflowExecutor();

const args = process.argv.slice(2);
const workflowId = args[0];

if (workflowId) {
  executor.executeWorkflow(workflowId)
    .then(result => {
      console.log('\n📊 Result:', JSON.stringify(result, null, 2));
      process.exit(result.success ? 0 : 1);
    })
    .catch(error => {
      console.error('❌ Workflow execution failed:', error);
      process.exit(1);
    });
} else {
  console.log('🚀 Executing all enabled workflows...\n');
  
  executor.executeAllWorkflows()
    .then(results => {
      const successCount = results.filter(r => r.success).length;
      console.log('\n' + '='.repeat(50));
      console.log('📊 Workflow Execution Summary');
      console.log('='.repeat(50));
      
      results.forEach(result => {
        const icon = result.success ? '✅' : '❌';
        console.log(`${icon} ${result.workflowId}: ${result.totalDuration}ms`);
      });
      
      console.log('\n' + '-'.repeat(50));
      console.log(`Total: ${successCount}/${results.length} workflows succeeded`);
      console.log('='.repeat(50));
      
      process.exit(successCount === results.length ? 0 : 1);
    })
    .catch(error => {
      console.error('❌ Workflow execution failed:', error);
      process.exit(1);
    });
}

export default WorkflowExecutor;