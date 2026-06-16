import type { RepoFile } from '../../github/types';
import { parseRepoUrl, type RepoSignals } from './repoLaunchReadiness';

function hasPath(files: RepoFile[], predicate: (path: string) => boolean): boolean {
  return files.some((file) => predicate(file.path.toLowerCase()));
}

export function buildRepoSignalsFromFiles(repoUrl: string, files: RepoFile[]): RepoSignals {
  const parsed = parseRepoUrl(repoUrl);
  return {
    owner: parsed?.owner ?? 'target',
    repo: parsed?.repo ?? 'repository',
    recentCommitCount: 0,
    branchProtectionActive: false,
    hasReadme: hasPath(files, (path) => path === 'readme.md'),
    hasLicense: hasPath(files, (path) => path === 'license' || path === 'license.md'),
    hasTests: hasPath(files, (path) => /\.(test|spec)\.[tj]sx?$/.test(path) || path.startsWith('tests/')),
    hasGithubWorkflows: hasPath(files, (path) => path.startsWith('.github/workflows/')),
    hasPackageJson: hasPath(files, (path) => path === 'package.json'),
    hasRuntimeValidation: hasPath(files, (path) => path.includes('runtimevalidation') || path.includes('/runtime/') || path.includes('/brain/') || path.includes('/llm/')),
  };
}
