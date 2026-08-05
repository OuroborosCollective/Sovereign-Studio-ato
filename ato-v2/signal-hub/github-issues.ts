import {
  SovereignGitHubRuntime,
  type SovereignGitHubEvidenceContext,
} from '../github/sovereign-github-runtime';

export interface GitHubIssueSignal {
  id: number;
  title: string;
  body: string | null;
  number: number;
  labels: readonly string[];
  url: string;
  state: string;
  createdAt: string;
  updatedAt: string;
  responseHash: string;
}

export interface SignalFilterOptions {
  labels?: readonly string[];
  state?: 'open' | 'closed' | 'all';
  since?: string;
}

export interface SignalAcknowledgement {
  statusLabel: 'processed' | 'failed' | 'in-progress';
  occurredAt: string;
  evidence: SovereignGitHubEvidenceContext;
}

export class GitHubIssueHub {
  private readonly runtime: SovereignGitHubRuntime;

  constructor(token: string) {
    this.runtime = new SovereignGitHubRuntime(token);
  }

  async fetchAutonomousSignals(
    owner: string,
    repo: string,
    options: SignalFilterOptions = {},
  ): Promise<readonly GitHubIssueSignal[]> {
    try {
      return await this.runtime.listIssueSignals({
        owner,
        repository: repo,
        state: options.state,
        labels: options.labels,
        since: options.since,
      });
    } catch (error: unknown) {
      const status = typeof error === 'object' && error !== null && 'status' in error
        ? Number((error as { status?: unknown }).status)
        : 0;
      const message = error instanceof Error ? error.message : 'unknown error';
      console.error(`[GitHubIssueHub] fetch error: ${message}`);
      if (status === 403) throw new Error('GitHub API rate limit hit');
      throw new Error(`Failed to sync GitHub signals: ${message}`);
    }
  }

  async acknowledgeSignal(
    owner: string,
    repo: string,
    issueNumber: number,
    acknowledgement: SignalAcknowledgement,
  ): Promise<void> {
    try {
      const commentReceipt = await this.runtime.createIssueComment({
        owner,
        repository: repo,
        issueNumber,
        body: [
          '### Sovereign Studio Autonomous Update',
          `Status: **${acknowledgement.statusLabel}**`,
          `Time: ${acknowledgement.occurredAt}`,
          '',
          'GitHub transport and independent comment readback are recorded separately.',
        ].join('\n'),
        evidence: acknowledgement.evidence,
      });
      if (commentReceipt.verdict !== 'VERIFIED') throw new Error('comment readback contradicted the requested effect');

      const labelReceipt = await this.runtime.addLabels({
        owner,
        repository: repo,
        issueNumber,
        labels: [acknowledgement.statusLabel],
        evidence: acknowledgement.evidence,
      });
      if (labelReceipt.verdict !== 'VERIFIED') throw new Error('label readback contradicted the requested effect');

      if (acknowledgement.statusLabel === 'processed') {
        const removalReceipt = await this.runtime.removeLabel({
          owner,
          repository: repo,
          issueNumber,
          label: 'autonomous-task',
          evidence: acknowledgement.evidence,
        });
        if (removalReceipt.verdict !== 'VERIFIED') throw new Error('label removal readback contradicted the requested effect');
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'unknown error';
      console.error(`[GitHubIssueHub] acknowledge error: ${message}`);
      throw new Error(`Failed to update signal status: ${message}`);
    }
  }
}

export const createGitHubSignalHub = (token: string): GitHubIssueHub => new GitHubIssueHub(token);
