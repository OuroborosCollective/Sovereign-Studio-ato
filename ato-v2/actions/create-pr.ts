import {
  createSovereignGitHubRuntime,
  type SovereignGitHubEvidenceContext,
} from '../github/sovereign-github-runtime';

interface PullRequestOptions {
  owner: string;
  repo: string;
  title: string;
  head: string;
  base: string;
  body?: string;
  labels?: string[];
  reviewers?: string[];
  evidence: SovereignGitHubEvidenceContext;
}

/**
 * Erstellt ausschließlich einen Draft-PR über die kanonische serverseitige
 * Octokit/REST-Grenze. Ein Transporterfolg wird durch einen unabhängigen
 * Pull-Readback bestätigt, bevor diese Funktion eine PR-Nummer zurückgibt.
 */
export async function createPullRequest(options: PullRequestOptions): Promise<number> {
  const {
    owner,
    repo,
    title,
    head,
    base,
    labels = ['automated', 'sovereign-v3'],
    reviewers = [],
    evidence,
  } = options;

  const prTemplate = [
    '## Sovereign Studio – revisionsgebundener Draft-PR',
    '',
    '### Beschreibung',
    options.body || 'Revisionsgebundene Änderung über die Sovereign GitHub Evidence-Grenze.',
    '',
    '### Truth Boundary',
    '- Dieser PR wird als Draft angelegt.',
    '- API-Erfolg allein beweist keine Wirkung.',
    '- Head, Base, Draft-Status und Head-SHA werden separat rückgelesen.',
    '- CI-, Merge-, Deployment- und Runtime-Erfolg werden hier nicht behauptet.',
  ].join('\n');

  try {
    const runtime = createSovereignGitHubRuntime();
    const verified = await runtime.createDraftPullRequest({
      owner,
      repository: repo,
      title,
      head,
      base,
      body: prTemplate,
      evidence,
    });

    if (labels.length > 0) {
      const labelReceipt = await runtime.addLabels({
        owner,
        repository: repo,
        issueNumber: verified.number,
        labels,
        evidence,
      });
      if (labelReceipt.verdict !== 'VERIFIED') {
        throw new Error('GitHub label readback contradicted the requested labels');
      }
    }

    if (reviewers.length > 0) {
      const reviewerReceipt = await runtime.requestReviewers({
        owner,
        repository: repo,
        pullNumber: verified.number,
        reviewers,
        evidence,
      });
      if (reviewerReceipt.verdict !== 'VERIFIED') {
        throw new Error('GitHub reviewer readback contradicted the requested reviewers');
      }
    }

    return verified.number;
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unbekannter API-Fehler';
    console.error(`[Sovereign Studio] GitHub-Operation fehlgeschlagen: ${message}`);
    throw error;
  }
}

export function generateBranchName(feature: string, identitySuffix: string): string {
  const sanitized = feature
    .toLowerCase()
    .split(' ').join('-')
    .split('/').join('-')
    .split('_').join('-')
    .split('.').join('-')
    .split(':').join('-')
    .split('@').join('-')
    .split('--').join('-');
  const suffix = identitySuffix.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 20);
  if (!sanitized || !suffix) throw new Error('Branch-Name benötigt Feature und deterministische Identität.');
  return `sovereign/feature/${sanitized}-${suffix}`;
}

export function validateRepositoryUrl(url: string): boolean {
  try {
    const validatedUrl = new URL(url);
    return validatedUrl.protocol === 'https:' && validatedUrl.hostname === 'github.com';
  } catch {
    return false;
  }
}
