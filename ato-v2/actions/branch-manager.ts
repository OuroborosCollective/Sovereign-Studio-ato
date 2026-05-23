import { execSync } from 'child_process';

/**
 * NOCode Studio V3: Branch Lifecycle Manager
 * Automates branch creation, naming conventions, and cleanup workflows
 * for AI-driven development pipelines.
 */

export type BranchType = 'feature' | 'bugfix' | 'hotfix' | 'refactor' | 'chore' | 'release';

export interface BranchMetadata {
  type: BranchType;
  issueId?: string | number;
  description: string;
}

export class BranchManager {
  private static readonly PREFIXES: Record<BranchType, string> = {
    feature: 'feat',
    bugfix: 'fix',
    hotfix: 'hotfix',
    refactor: 'refactor',
    chore: 'chore',
    release: 'release'
  };

  /**
   * Generates a standardized branch name based on project conventions.
   * Avoids global regex replace as per core constraints.
   */
  public static generateBranchName(meta: BranchMetadata): string {
    const prefix = this.PREFIXES[meta.type];
    
    // Normalize description: lowercase and replace non-alphanumeric with hyphens
    const normalizedDesc = meta.description
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(Boolean)
      .join('-');

    const baseName = meta.issueId 
      ? `${prefix}/${meta.issueId}-${normalizedDesc}`
      : `${prefix}/${normalizedDesc}`;

    return baseName.slice(0, 100); // Guard against OS path limits
  }

  /**
   * Validates if a branch name follows the NOCode Studio architecture.
   */
  public static isValidBranchName(name: string): boolean {
    const validPrefixes = Object.values(this.PREFIXES).join('|');
    const pattern = new RegExp(`^(${validPrefixes})\\/([a-z0-9-]+)$`);
    return pattern.test(name);
  }

  /**
   * Identifies branches that have been merged and can be safely deleted.
   */
  public static getStaleBranches(mainBranch: string = 'main'): string[] {
    try {
      const mergedBranches = execSync(`git branch --merged ${mainBranch}`)
        .toString()
        .split('\n')
        .map(b => b.trim())
        .filter(b => b && b !== mainBranch && !b.startsWith('*'));
      
      return mergedBranches;
    } catch (error) {
      console.error('Failed to fetch merged branches:', error);
      return [];
    }
  }

  /**
   * Orchestrates the cleanup of local and remote stale branches.
   */
  public static async cleanupStaleBranches(mainBranch: string = 'main'): Promise<{ deleted: string[]; failed: string[] }> {
    const stale = this.getStaleBranches(mainBranch);
    const result = { deleted: [] as string[], failed: [] as string[] };

    for (const branch of stale) {
      try {
        // Protect protected branches explicitly
        if (['main', 'master', 'develop', 'staging'].includes(branch)) continue;

        execSync(`git branch -d ${branch}`);
        result.deleted.push(branch);
      } catch (e) {
        result.failed.push(branch);
      }
    }

    return result;
  }

  /**
   * Formats a commit message following Conventional Commits, 
   * used when bridging branch context to repository updates.
   */
  public static formatCommitMessage(type: BranchType, scope: string, message: string): string {
    const typeKey = this.PREFIXES[type];
    const cleanScope = scope.split(/[^a-z0-9]+/).filter(Boolean).join('-');
    return `${typeKey}(${cleanScope}): ${message}`;
  }
}

export default BranchManager;