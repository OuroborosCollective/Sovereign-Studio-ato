import { Octokit } from 'octokit';

/**
 * GitHubIssueSignal
 * Definiert die Struktur eines Signals, das aus einem GitHub Issue extrahiert wurde.
 */
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

/**
 * SignalFilterOptions
 * Filteroptionen für die Synchronisation von Issues.
 */
export interface SignalFilterOptions {
  labels?: string[];
  state?: 'open' | 'closed' | 'all';
  since?: string;
}

/**
 * GitHubIssueHub
 * Kern-Komponente zur Integration von GitHub Issues als Signal-Quelle für den 
 * autonomen Sovereign Studio Cycle. Ermöglicht die Steuerung von Entwicklungsaufgaben
 * direkt über das GitHub-Repository.
 */
export class GitHubIssueHub {
  private octokit: Octokit;

  constructor(token: string) {
    /**
     * Initialisierung des Octokit Clients. 
     * Verwendet die offizielle 'octokit' Bibliothek zur Interaktion mit der GitHub REST API.
     */
    this.octokit = new Octokit({
      auth: token,
    });
  }

  /**
   * Holt Issues, die für den autonomen Entwicklungszyklus markiert sind.
   * Filtert standardmäßig nach 'autonomous-task' und schließt Pull Requests aus.
   */
  async fetchAutonomousSignals(
    owner: string,
    repo: string,
    options: SignalFilterOptions = {}
  ): Promise<GitHubIssueSignal[]> {
    try {
      const { data: issues } = await this.octokit.rest.issues.listForRepo({
        owner,
        repo,
        state: options.state || 'open',
        labels: options.labels?.join(',') || 'autonomous-task',
        since: options.since,
        sort: 'updated',
        direction: 'desc',
      });

      /**
       * Die GitHub REST API inkludiert Pull Requests in der Issue-Liste. 
       * Wir filtern diese explizit aus, da der Sovereign Studio Cycle auf reinen Issue-Instruktionen basiert.
       */
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
    } catch (error: any) {
      console.error('[GitHubIssueHub] Error fetching signals:', error);
      throw new Error(`Failed to synchronize with GitHub Signal Hub: ${error.message}`);
    }
  }

  /**
   * Aktualisiert den Status eines Signals im Repository nach der Verarbeitung 
   * durch den Sovereign Studio Assistant. Hinterlässt einen Audit-Log Kommentar.
   */
  async acknowledgeSignal(
    owner: string,
    repo: string,
    issueNumber: number,
    statusLabel: 'processed' | 'failed' | 'in-progress'
  ): Promise<void> {
    try {
      // Kommentar für den Audit-Trail im GitHub Issue hinterlassen
      await this.octokit.rest.issues.createComment({
        owner,
        repo,
        issue_number: issueNumber,
        body: `### [Sovereign Studio Design-Coder] Autonomous Cycle Update\nStatus set to: **${statusLabel}**\n*Timestamp: ${new Date().toISOString()}*`,
      });

      // Status-Label aktualisieren
      await this.octokit.rest.issues.addLabels({
        owner,
        repo,
        issue_number: issueNumber,
        labels: [statusLabel],
      });

      // Optional: Entferne das ursprüngliche 'autonomous-task' Label, wenn 'processed' erreicht wurde
      if (statusLabel === 'processed') {
        try {
          await this.octokit.rest.issues.removeLabel({
            owner,
            repo,
            issue_number: issueNumber,
            name: 'autonomous-task',
          });
        } catch (e) {
          // Fehler ignorieren, falls das Label bereits manuell entfernt wurde
        }
      }
    } catch (error: any) {
      console.error('[GitHubIssueHub] Error acknowledging signal:', error);
      throw new Error(`Failed to update GitHub Signal status: ${error.message}`);
    }
  }
}

/**
 * Fabrikfunktion zur Initialisierung des GitHub Signal Hubs.
 */
export const createGitHubSignalHub = (token: string): GitHubIssueHub => new GitHubIssueHub(token);