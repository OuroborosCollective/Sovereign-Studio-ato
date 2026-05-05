import { Octokit } from '@octokit/rest';

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

/**
 * GitHubIssueHub
 * Integriert GitHub Issues als Signal-Quelle für den autonomen Sovereign Studio Cycle.
 * Nutzt Octokit zur Kommunikation mit der GitHub REST API.
 */
export class GitHubIssueHub {
  private octokit: Octokit;

  constructor(token: string) {
    this.octokit = new Octokit({
      auth: token,
    });
  }

  /**
   * Holt Issues, die für den autonomen Entwicklungszyklus markiert sind.
   * Standardmäßig wird nach dem Label 'autonomous-task' gefiltert.
   */
  async fetchAutonomousSignals(
    owner: string,
    repo: string,
    options: SignalFilterOptions = {}
  ): Promise<GitHubIssueSignal[]> {
    try {
      const { data: issues } = await this.octokit.issues.listForRepo({
        owner,
        repo,
        state: options.state || 'open',
        labels: options.labels?.join(',') || 'autonomous-task',
        since: options.since,
        sort: 'updated',
        direction: 'desc',
      });

      // GitHub API inkludiert Pull Requests in der Issue-Liste. 
      // Wir filtern diese explizit aus, falls sie keine reinen Issues sind.
      return issues
        .filter((issue) => !issue.pull_request)
        .map((issue) => ({
          id: issue.id,
          title: issue.title,
          body: issue.body ?? '',
          number: issue.number,
          labels: issue.labels.map((label) => 
            typeof label === 'string' ? label : (label.name ?? '')
          ),
          url: issue.html_url,
          state: issue.state,
          createdAt: issue.created_at,
          updatedAt: issue.updated_at,
        }));
    } catch (error) {
      console.error('[GitHubIssueHub] Error fetching signals:', error);
      throw new Error('Failed to synchronize with GitHub Signal Hub');
    }
  }

  /**
   * Aktualisiert ein Issue nach der Verarbeitung durch den Sovereign Studio Assistant.
   */
  async acknowledgeSignal(
    owner: string,
    repo: string,
    issueNumber: number,
    statusLabel: 'processed' | 'failed' | 'in-progress'
  ): Promise<void> {
    try {
      await this.octokit.issues.createComment({
        owner,
        repo,
        issue_number: issueNumber,
        body: `[Sovereign Studio V3] Autonomous Cycle Update: Status set to ${statusLabel}`,
      });

      await this.octokit.issues.addLabels({
        owner,
        repo,
        issue_number: issueNumber,
        labels: [statusLabel],
      });
    } catch (error) {
      console.error('[GitHubIssueHub] Error acknowledging signal:', error);
    }
  }
}

export const createGitHubSignalHub = (token: string) => new GitHubIssueHub(token);