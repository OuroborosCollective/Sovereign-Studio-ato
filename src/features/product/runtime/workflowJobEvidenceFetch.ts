import { buildGitHubHeaders } from '../../github/githubAuthSession';
import { parseGithubRepoUrl } from '../../github/utils';
import { extractWorkflowJobEvidence, type WorkflowJobEvidenceReport } from './workflowJobEvidence';

export interface WorkflowJobEvidenceFetchInput {
  repoUrl: string;
  runId: string;
  token?: string;
  fetcher?: typeof fetch;
}

interface GitHubJobsResponse {
  jobs?: Array<{ id?: number; name?: string; conclusion?: string | null }>;
}

export interface WorkflowJobEvidenceFetchResult {
  ok: boolean;
  reports: WorkflowJobEvidenceReport[];
  warnings: string[];
  summary: string;
}

export async function fetchWorkflowJobEvidence(input: WorkflowJobEvidenceFetchInput): Promise<WorkflowJobEvidenceFetchResult> {
  const parsed = parseGithubRepoUrl(input.repoUrl);
  if (!parsed) return { ok: false, reports: [], warnings: ['Invalid repository URL.'], summary: 'Workflow job evidence fetch skipped: invalid repository URL.' };
  if (!input.runId.trim()) return { ok: false, reports: [], warnings: ['Missing workflow run id.'], summary: 'Workflow job evidence fetch skipped: missing run id.' };

  const fetcher = input.fetcher ?? fetch;
  const headers = buildGitHubHeaders({ token: input.token });
  const apiBase = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}`;
  const warnings: string[] = [];
  const reports: WorkflowJobEvidenceReport[] = [];

  const jobsResponse = await fetcher(`${apiBase}/actions/runs/${encodeURIComponent(input.runId)}/jobs`, { headers });
  if (!jobsResponse.ok) {
    return { ok: false, reports, warnings: [`Jobs endpoint returned ${jobsResponse.status}.`], summary: `Workflow job evidence fetch failed with ${jobsResponse.status}.` };
  }

  const payload = await jobsResponse.json() as GitHubJobsResponse;
  const jobs = (payload.jobs ?? []).filter((job) => job.id && (job.conclusion === 'failure' || job.conclusion === 'cancelled' || job.conclusion === 'timed_out'));

  for (const job of jobs.slice(0, 5)) {
    const name = job.name ?? `job-${job.id}`;
    try {
      const logResponse = await fetcher(`${apiBase}/actions/jobs/${job.id}/logs`, { headers });
      if (!logResponse.ok) {
        warnings.push(`Job ${name} log endpoint returned ${logResponse.status}.`);
        continue;
      }
      const logText = await logResponse.text();
      reports.push(extractWorkflowJobEvidence({ jobName: name, logText }));
    } catch (error) {
      warnings.push(error instanceof Error ? error.message : `Job ${name} log request failed.`);
    }
  }

  return {
    ok: warnings.length === 0,
    reports,
    warnings,
    summary: `${reports.length} workflow job evidence report(s), ${warnings.length} warning(s).`,
  };
}
