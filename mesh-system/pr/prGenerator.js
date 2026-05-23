import fs from 'node:fs/promises';
import path from 'node:path';
import { execSync } from 'node:child_process';

/**
 * PRGenerator: Core component of the Ghost-Pilot autonomous cycle.
 * Orchestrates file persistence, branch management, and PR metadata generation
 * within the NOCode Studio hybrid architecture.
 */
class PRGenerator {
  constructor(config = {}) {
    this.baseDir = process.cwd();
    this.stagingDir = path.join(this.baseDir, '.sovereign', 'staging');
    this.metadataDir = path.join(this.baseDir, '.sovereign', 'metadata');
  }

  /**
   * Initializes the directory structure for PR preparation.
   */
  async initialize() {
    await fs.mkdir(this.stagingDir, { recursive: true });
    await fs.mkdir(this.metadataDir, { recursive: true });
  }

  /**
   * Persists agent-generated code to the target filesystem.
   * @param {Array<{path: string, content: string}>} files 
   */
  async persistOutputs(files) {
    for (const file of files) {
      const fullPath = path.join(this.baseDir, file.path);
      const dir = path.dirname(fullPath);
      
      await fs.mkdir(dir, { recursive: true });
      await fs.writeFile(fullPath, file.content, 'utf8');
      
      console.log(`[PRGenerator] Persisted: ${file.path}`);
    }
  }

  /**
   * Prepares a Git branch for the new PR.
   * @param {string} taskName 
   * @returns {string} branchName
   */
  prepareBranch(taskName) {
    const sanitizedTask = taskName.split(' ').join('-').toLowerCase();
    const branchName = `ghost-pilot/${sanitizedTask}-${Date.now()}`;
    
    try {
      execSync(`git checkout -b ${branchName}`, { stdio: 'ignore' });
      return branchName;
    } catch (error) {
      console.error('[PRGenerator] Failed to create branch:', error.message);
      throw error;
    }
  }

  /**
   * Generates the Pull Request template based on agent telemetry.
   * @param {Object} metadata 
   * @returns {string} PR body markdown
   */
  generatePRTemplate(metadata) {
    const { title, description, impacts, aiModel } = metadata;
    
    return `
# Ghost-Pilot PR: ${title}

## Overview
${description}

## Technical Impact (NOCode Studio Mesh)
${impacts.map(i => `- ${i}`).join('\n')}

## AI Generation Metadata
- **Engine:** ${aiModel}
- **Stack:** Vite + Capacitor 6
- **Architecture:** NOCode Studio Build-to-Deploy

---
*Generated autonomously by NOCode Studio Ghost-Pilot.*
    `.trim();
  }

  /**
   * Commits and prepares the PR for the Autonomous-Cycle.
   * @param {Object} prData 
   */
  async createPullRequest(prData) {
    const { files, title, description, impacts, aiModel } = prData;

    await this.initialize();
    
    // 1. Create unique branch
    const branchName = this.prepareBranch(title);
    
    // 2. Persist code changes
    await this.persistOutputs(files);
    
    // 3. Generate PR Description
    const prBody = this.generatePRTemplate({ title, description, impacts, aiModel });
    const prBodyPath = path.join(this.metadataDir, `${branchName}.md`);
    await fs.writeFile(prBodyPath, prBody, 'utf8');

    // 4. Git Commit Cycle
    try {
      execSync('git add .');
      execSync(`git commit -m "feat(ghost-pilot): ${title}"`);
      
      console.log(`[PRGenerator] Changes staged and committed on branch ${branchName}`);
      console.log(`[PRGenerator] PR Metadata saved at ${prBodyPath}`);
      
      return {
        branch: branchName,
        metadataPath: prBodyPath,
        status: 'READY_FOR_PUSH'
      };
    } catch (error) {
      console.error('[PRGenerator] Git commit failed:', error.message);
      throw error;
    }
  }
}

export default PRGenerator;