import { Octokit } from 'octokit';

export interface GitHubIssueSignal {
  id: number;
  title: string;
  body: string | null;
  number: number;
  labels: string[];
  url: string;
  state: string;
  createdAt: string;
  updatedAt: string;
}

export interface SignalFilterOptions {
  labels?: string[];
  state?: 'open' | 'closed' | 'all';
  since?: string;
}

export class GitHubIssueHub {
  private octokit: Octokit;

  constructor(token: string) {
    this.octokit = new Octokit({
      auth: token,
    });
  }

  async fetchAutonomousSignals(
    owner: string,
    repo: string,
    options: SignalFilterOptions = {}
  ): Promise<GitHubIssueSignal[]> {
    try {
      const response = await this.octokit.rest.issues.listForRepo({
        owner,
        repo,
        state: options.state || 'open',
        labels: options.labels?.join(',') || 'autonomous-task',
        since: options.since,
        sort: 'updated',
        direction: 'desc',
        per_page: 100,
      });

      return response.data
        .filter((issue) => !('pull_request' in issue))
        .map((issue) => ({
          id: issue.id,
          title: issue.title,
          body: issue.body ?? '',
          number: issue.number,
          labels: (issue.labels || []).map((label) =>
            typeof label === 'string'
              ? label
              : label?.name ?? ''
          ).filter(Boolean),
          url: issue.html_url,
          state: issue.state,
          createdAt: issue.created_at,
          updatedAt: issue.updated_at,
        }));

    } catch (error: any) {
      console.error('[GitHubIssueHub] fetch error:', error?.message);

      if (error?.status === 403) {
        throw new Error('GitHub API rate limit hit');
      }

      throw new Error(
        `Failed to sync GitHub signals: ${error?.message || 'unknown error'}`
      );
    }
  }

  async acknowledgeSignal(
    owner: string,
    repo: string,
    issueNumber: number,
    statusLabel: 'processed' | 'failed' | 'in-progress'
  ): Promise<void> {
    try {
      const timestamp = new Date().toISOString();

      await this.octokit.rest.issues.createComment({
        owner,
        repo,
        issue_number: issueNumber,
        body: [
          '### 🤖 Sovereign Studio Autonomous Update',
          `Status: **${statusLabel}**`,
          `Time: ${timestamp}`,
        ].join('\n'),
      });

      await this.octokit.rest.issues.addLabels({
        owner,
        repo,
        issue_number: issueNumber,
        labels: [statusLabel],
      });

      if (statusLabel === 'processed') {
        try {
          await this.octokit.rest.issues.removeLabel({
            owner,
            repo,
            issue_number: issueNumber,
            name: 'autonomous-task',
          });
        } catch {
          // silent: label may not exist
        }
      }

    } catch (error: any) {
      console.error('[GitHubIssueHub] acknowledge error:', error?.message);

      throw new Error(
        `Failed to update signal status: ${error?.message || 'unknown error'}`
      );
    }
  }
}

export const createGitHubSignalHub = (token: string): GitHubIssueHub =>
  new GitHubIssueHub(token);
