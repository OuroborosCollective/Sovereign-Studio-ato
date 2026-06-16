export type ToolStageState = 'pending' | 'running' | 'done' | 'failed';

export type ToolStageId =
  | 'safe_repo_inspection'
  | 'task_extraction'
  | 'readiness_eval'
  | 'checklist_generation'
  | 'copywriting'
  | 'workflow_watch';

export interface ToolProgressStage {
  id: ToolStageId;
  label: string;
  description: string;
  state: ToolStageState;
}

export interface RepoSignals {
  owner: string;
  repo: string;
  description?: string;
  language?: string;
  stars?: number;
  forks?: number;
  recentCommitCount?: number;
  openIssues?: number;
  openPullRequests?: number;
  branchProtectionActive?: boolean;
  hasReadme?: boolean;
  hasLicense?: boolean;
  hasTests?: boolean;
  hasGithubWorkflows?: boolean;
  hasPackageJson?: boolean;
  hasRuntimeValidation?: boolean;
}

export interface ReadinessRisk {
  id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  mitigation: string;
}

export interface OwnerChecklistItem {
  id: string;
  owner: 'Lead Engineer' | 'Reviewer' | 'QA Agent' | 'Product Owner' | 'DevOps';
  text: string;
  done: boolean;
}

export interface RepoReadinessReport {
  score: number;
  grade: 'EXCELLENT' | 'HEALTHY' | 'RISK' | 'BLOCKED';
  releaseStateReached: boolean;
  summary: string;
  risks: ReadinessRisk[];
  checklist: OwnerChecklistItem[];
}

export const DEFAULT_TOOL_PROGRESS_RAIL: ToolProgressStage[] = [
  {
    id: 'safe_repo_inspection',
    label: 'Safe GitHub signals check',
    description: 'Inspect owner, repo metadata, branches, issues, PRs and safe public signals.',
    state: 'pending',
  },
  {
    id: 'task_extraction',
    label: 'Constraints task extraction',
    description: 'Turn the user brief into strict implementation boundaries.',
    state: 'pending',
  },
  {
    id: 'readiness_eval',
    label: 'Launch footprint matching',
    description: 'Score docs, tests, workflows, validation and branch safety.',
    state: 'pending',
  },
  {
    id: 'checklist_generation',
    label: 'Owner duty checklist setup',
    description: 'Create concrete follow-up duties for owner, reviewer, QA and DevOps.',
    state: 'pending',
  },
  {
    id: 'copywriting',
    label: 'Notification copy outlines',
    description: 'Prepare release or PR body sections from the verified context.',
    state: 'pending',
  },
  {
    id: 'workflow_watch',
    label: 'Workflow watch',
    description: 'Wait for GitHub checks and surface every status transition.',
    state: 'pending',
  },
];

export function parseRepoUrl(url: string): { owner: string; repo: string } | null {
  const cleaned = url.trim().replace(/^https?:\/\/(www\.)?github\.com\//i, '');
  const parts = cleaned.split('/').filter(Boolean);
  if (parts.length < 2) return null;
  return {
    owner: parts[0],
    repo: parts[1].replace(/\.git$/i, ''),
  };
}

export function stableContextHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function clampScore(score: number): number {
  return Math.max(0, Math.min(100, Math.round(score)));
}

function gradeFor(score: number, blocked: boolean): RepoReadinessReport['grade'] {
  if (blocked) return 'BLOCKED';
  if (score >= 85) return 'EXCELLENT';
  if (score >= 65) return 'HEALTHY';
  return 'RISK';
}

export function evaluateRepoReadiness(signals: RepoSignals): RepoReadinessReport {
  const risks: ReadinessRisk[] = [];
  let score = 30;

  if (signals.hasReadme) score += 12;
  else risks.push({ id: 'missing-readme', severity: 'high', title: 'README missing or not detected', mitigation: 'Generate README.md before merge.' });

  if (signals.hasLicense) score += 8;
  else risks.push({ id: 'missing-license', severity: 'medium', title: 'License missing or not detected', mitigation: 'Add a LICENSE file or document private/internal status.' });

  if (signals.hasTests) score += 14;
  else risks.push({ id: 'missing-tests', severity: 'high', title: 'Tests missing or not detected', mitigation: 'Add Vitest, smoke or repository-specific checks.' });

  if (signals.hasGithubWorkflows) score += 14;
  else risks.push({ id: 'missing-workflows', severity: 'high', title: 'GitHub workflows missing', mitigation: 'Add CI workflow for type-check, lint, tests and build.' });

  if (signals.hasRuntimeValidation) score += 8;
  else risks.push({ id: 'missing-runtime-validation', severity: 'medium', title: 'Runtime validation weak', mitigation: 'Add runtime verification before provider output reaches GitHub.' });

  if ((signals.recentCommitCount ?? 0) >= 5) score += 8;
  else if ((signals.recentCommitCount ?? 0) > 0) score += 4;
  else risks.push({ id: 'stale-commits', severity: 'low', title: 'No recent commits detected', mitigation: 'Confirm repository activity before launch.' });

  if (signals.branchProtectionActive) score += 6;
  else risks.push({ id: 'branch-protection', severity: 'medium', title: 'Branch protection not confirmed', mitigation: 'Require PR checks before merge on default branch.' });

  if ((signals.openPullRequests ?? 0) > 5) {
    score -= 5;
    risks.push({ id: 'many-open-prs', severity: 'medium', title: 'Many open pull requests', mitigation: 'Triage or close stale PRs before release.' });
  }

  const blocked = risks.some((risk) => risk.severity === 'critical') || (!signals.hasReadme && !signals.hasGithubWorkflows);
  const finalScore = clampScore(score);
  const grade = gradeFor(finalScore, blocked);

  return {
    score: finalScore,
    grade,
    releaseStateReached: grade === 'EXCELLENT' || (grade === 'HEALTHY' && risks.every((risk) => risk.severity !== 'high')),
    summary: `${signals.owner}/${signals.repo}: ${finalScore}/100 ${grade}`,
    risks,
    checklist: buildOwnerChecklist(signals, risks),
  };
}

export function buildOwnerChecklist(signals: RepoSignals, risks: ReadinessRisk[] = []): OwnerChecklistItem[] {
  const items: OwnerChecklistItem[] = [
    {
      id: 'docs-readme',
      owner: 'Lead Engineer',
      text: signals.hasReadme ? 'Review README for accuracy.' : 'Create README.md with setup, usage and architecture notes.',
      done: Boolean(signals.hasReadme),
    },
    {
      id: 'ci-workflows',
      owner: 'DevOps',
      text: signals.hasGithubWorkflows ? 'Verify CI workflow names and required checks.' : 'Add GitHub workflow for type-check, lint, tests and build.',
      done: Boolean(signals.hasGithubWorkflows),
    },
    {
      id: 'tests-runtime',
      owner: 'QA Agent',
      text: signals.hasTests ? 'Run and verify existing tests.' : 'Add regression test for the generated change path.',
      done: Boolean(signals.hasTests),
    },
    {
      id: 'risk-review',
      owner: 'Reviewer',
      text: risks.length ? `Review ${risks.length} readiness risk(s).` : 'Approve launch readiness risk register.',
      done: risks.length === 0,
    },
    {
      id: 'product-copy',
      owner: 'Product Owner',
      text: 'Prepare release notes, PR summary and follow-up questions.',
      done: false,
    },
  ];

  return items;
}

export function buildLaunchPackageMarkdown(signals: RepoSignals, report: RepoReadinessReport, constraints: string): string {
  const risks = report.risks.length
    ? report.risks.map((risk) => `- **${risk.severity.toUpperCase()}** ${risk.title}: ${risk.mitigation}`).join('\n')
    : '- No blocking readiness risks detected.';

  const checklist = report.checklist.map((item) => `- [${item.done ? 'x' : ' '}] **${item.owner}**: ${item.text}`).join('\n');

  return `# Launch Readiness Package: ${signals.repo}\n\n## Summary\n\n${report.summary}\n\nConstraints:\n\n${constraints || 'No explicit constraints provided.'}\n\n## Risk Register\n\n${risks}\n\n## Owner Checklist\n\n${checklist}\n\n## Release State\n\n${report.releaseStateReached ? 'RELEASE STATE REACHED' : 'RELEASE STATE NOT REACHED'}\n`;
}
