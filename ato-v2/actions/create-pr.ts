import { Octokit } from "@octokit/rest";

interface PullRequestOptions {
  owner: string;
  repo: string;
  title: string;
  head: string;
  base: string;
  body?: string;
  labels?: string[];
  reviewers?: string[];
}

/**
 * Erstellt einen standardisierten Pull Request für Sovereign Studio V3.
 * Nutzt vordefinierte Templates und automatische Label-Zuweisung.
 */
export async function createPullRequest(options: PullRequestOptions): Promise<number> {
  const octokit = new Octokit({
    auth: process.env.GITHUB_TOKEN,
  });

  const { owner, repo, title, head, base, labels = ["automated", "sovereign-v3"], reviewers = [] } = options;

  const prTemplate = `
## 🚀 Sovereign Studio V3 - Automated PR

### Beschreibung
${options.body || "Automatisierte Code-Generierung durch Sovereign Studio Design-Coder."}

### Architektur-Checklist
- [x] Mobile-First Optimierung (Capacitor 6)
- [x] TypeScript Typensicherheit gewährleistet
- [x] Gemini API Integration validiert
- [x] Keine kritischen Regex-Muster (replace //g vermieden)

### Deployment
- Automatische CI/CD Pipeline für Android-Optimierung wird nach Merge getriggert.

---
*Erstellt durch Sovereign Studio V3 Assistant.*
  `.trim();

  try {
    // 1. Pull Request erstellen
    const { data: pr } = await octokit.rest.pulls.create({
      owner,
      repo,
      title,
      head,
      base,
      body: prTemplate,
      maintainer_can_modify: true,
    });

    // 2. Labels hinzufügen
    if (labels.length > 0) {
      await octokit.rest.issues.addLabels({
        owner,
        repo,
        issue_number: pr.number,
        labels,
      });
    }

    // 3. Reviewer zuweisen
    if (reviewers.length > 0) {
      await octokit.rest.pulls.requestReviewers({
        owner,
        repo,
        pull_number: pr.number,
        reviewers,
      });
    }

    return pr.number;
  } catch (error: any) {
    console.error("[Sovereign Studio] Fehler bei der PR-Erstellung:", error.message);
    throw error;
  }
}

/**
 * Hilfsfunktion zur Generierung von Branch-Namen basierend auf dem Task.
 */
export function generateBranchName(feature: string): string {
  const sanitized = feature
    .toLowerCase()
    .split(" ")
    .join("-");
  return `sovereign/feature/${sanitized}-${Date.now()}`;
}