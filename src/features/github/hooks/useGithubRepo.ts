import { useState } from 'react';
import {
  clearDurableRepoSnapshot,
  createDurableRepoSnapshot,
  loadDurableRepoSnapshot,
  saveDurableRepoSnapshot,
  type DurableRepoSnapshot,
} from '../repoSnapshotPersistence';
import { toolchainApi } from '../../toolchain/toolchainApi';
import { RepoFile } from '../types';
import { parseGithubRepoUrl } from '../utils';
import {
  canUseSovereignDependency,
  createSovereignDependencyLifecycleState,
  recordSovereignDependencyFailure,
  recordSovereignDependencySuccess,
  startSovereignDependencyCheck,
  type SovereignDependencyLifecycleState,
} from '../../product/runtime/sovereignDependencyLifecycle';
import { publishSovereignDependencyCoachSignal } from '../../product/runtime/sovereignDependencyCoachBridge';

export interface LoadRepoTreeOptions {
  repoUrl?: string;
  repoBranch?: string;
}

const GITHUB_REPO_DEPENDENCY_KEY = 'github-repo-tree';

function createGithubRepoDependency(): SovereignDependencyLifecycleState {
  return createSovereignDependencyLifecycleState(
    GITHUB_REPO_DEPENDENCY_KEY,
    'github',
    'GitHub repository tree has not been checked yet.',
  );
}

function publishDependencySignal(dependency: SovereignDependencyLifecycleState): void {
  publishSovereignDependencyCoachSignal(dependency);
}

function readInitialSnapshot(): DurableRepoSnapshot | null {
  if (typeof window === 'undefined') return null;
  return loadDurableRepoSnapshot(window.localStorage);
}

function persistSnapshot(input: { repoUrl: string; repoBranch: string; repoStatus: string; repoFiles: RepoFile[] }): void {
  if (typeof window === 'undefined') return;
  saveDurableRepoSnapshot(window.localStorage, createDurableRepoSnapshot(input));
}

export const useGithubRepo = () => {
  const [initialSnapshot] = useState(readInitialSnapshot);
  const [repoUrl, setRepoUrl] = useState(initialSnapshot?.repoUrl ?? '');
  const [repoBranch, setRepoBranch] = useState(initialSnapshot?.repoBranch ?? '');
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>(initialSnapshot?.repoFiles ?? []);
  const [repoStatus, setRepoStatus] = useState(initialSnapshot ? `${initialSnapshot.repoStatus} [durable restored]` : 'Noch kein echtes Repo geladen.');
  const [isRepoBusy, setIsRepoBusy] = useState(false);
  const [githubDependencyLifecycle, setGithubDependencyLifecycle] = useState(createGithubRepoDependency);

  const restoreRepoSnapshot = (next: {
    repoUrl: string;
    repoBranch: string;
    repoStatus: string;
    repoFiles: RepoFile[];
  }) => {
    const safeFiles = next.repoFiles.filter((file) => file.type === 'blob' || file.type === 'tree').slice(0, 500);
    const nextStatus = `${next.repoStatus} [session restored]`;
    setRepoUrl(next.repoUrl);
    setRepoBranch(next.repoBranch);
    setRepoStatus(nextStatus);
    setRepoFiles(safeFiles);
    setGithubDependencyLifecycle((state) => {
      const nextState = recordSovereignDependencySuccess(state, 'GitHub repo restored from session snapshot.').state;
      publishDependencySignal(nextState);
      return nextState;
    });
    persistSnapshot({ repoUrl: next.repoUrl, repoBranch: next.repoBranch, repoStatus: nextStatus, repoFiles: safeFiles });
  };

  const clearRepoSnapshot = () => {
    const nextState = createGithubRepoDependency();
    setRepoFiles([]);
    setRepoStatus('Noch kein echtes Repo geladen.');
    setGithubDependencyLifecycle(nextState);
    publishDependencySignal(nextState);
    if (typeof window !== 'undefined') clearDurableRepoSnapshot(window.localStorage);
  };

  const loadRepoTree = async (options: LoadRepoTreeOptions = {}) => {
    const nextRepoUrl = (options.repoUrl ?? repoUrl).trim();
    const nextRepoBranch = (options.repoBranch ?? repoBranch).trim();

    if (options.repoUrl !== undefined) setRepoUrl(nextRepoUrl);
    if (options.repoBranch !== undefined) setRepoBranch(nextRepoBranch);

    const parsed = parseGithubRepoUrl(nextRepoUrl);

    if (!parsed) {
      const nextState = recordSovereignDependencyFailure(githubDependencyLifecycle, {}, 'Invalid GitHub repository URL.').state;
      setGithubDependencyLifecycle(nextState);
      publishDependencySignal(nextState);
      setRepoStatus('Ungültige GitHub URL');
      setRepoFiles([]);
      return;
    }

    if (!canUseSovereignDependency(githubDependencyLifecycle)) {
      const nextState = startSovereignDependencyCheck(githubDependencyLifecycle).state;
      setGithubDependencyLifecycle(nextState);
      publishDependencySignal(nextState);
      setRepoStatus('GitHub Repo-Ladepfad ist kurz blockiert. Bitte nach Circuit-Cooldown erneut versuchen.');
      setRepoFiles([]);
      return;
    }

    let dependencyState = startSovereignDependencyCheck(githubDependencyLifecycle).state;
    setGithubDependencyLifecycle(dependencyState);
    publishDependencySignal(dependencyState);
    setIsRepoBusy(true);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);

    try {
      const branches = await toolchainApi.listBranches({ owner: parsed.owner, repo: parsed.repo });
      const availableBranches = branches.branches
        .map((item) => item.name.trim())
        .filter(Boolean);
      const branchToLoad = nextRepoBranch || (availableBranches.includes('main') ? 'main' : availableBranches[0]);
      if (!branchToLoad) throw new Error('Der Sovereign-Gateway lieferte keinen verfügbaren Branch.');
      if (nextRepoBranch && !availableBranches.includes(nextRepoBranch)) {
        throw new Error(`Branch '${nextRepoBranch}' ist über den Sovereign-Gateway nicht verfügbar.`);
      }

      const queue = [''];
      const visited = new Set<string>();
      const files: RepoFile[] = [];
      while (queue.length > 0 && files.length < 500) {
        const directory = queue.shift() ?? '';
        if (visited.has(directory)) continue;
        visited.add(directory);
        const response = await toolchainApi.listDirectory({
          owner: parsed.owner,
          repo: parsed.repo,
          path: directory,
          ref: branchToLoad,
        });
        // ⚡ Bolt: Fast native lexicographical string comparison replacing slow localeCompare during recursive directory tree sorting
        const entries = [...response.items].sort((left, right) => (
          left.path < right.path ? -1 : left.path > right.path ? 1 : 0
        ));
        for (const entry of entries) {
          if (files.length >= 500) break;
          const type = entry.type === 'file' ? 'blob' : 'tree';
          files.push({ path: entry.path, type, size: entry.size ?? undefined });
          if (type === 'tree' && !visited.has(entry.path)) queue.push(entry.path);
        }
      }

      const nextStatus = `${files.length} echte Repo-Einträge über den Sovereign-Gateway geladen (${branchToLoad})`;
      setRepoFiles(files);
      setRepoBranch(branchToLoad);
      setRepoStatus(nextStatus);
      dependencyState = recordSovereignDependencySuccess(dependencyState, `GitHub repo tree loaded: ${parsed.owner}/${parsed.repo}.`).state;
      setGithubDependencyLifecycle(dependencyState);
      publishDependencySignal(dependencyState);
      persistSnapshot({ repoUrl: nextRepoUrl, repoBranch: branchToLoad, repoStatus: nextStatus, repoFiles: files });
      console.log(`Repo geladen: ${parsed.owner}/${parsed.repo}`);
    } catch (err) {
      console.error(err);
      setRepoFiles([]);
      const safeMessage = err instanceof Error ? err.message : 'Fehler beim Laden des Repos';
      const nextState = recordSovereignDependencyFailure(dependencyState, {}, safeMessage).state;
      setGithubDependencyLifecycle(nextState);
      publishDependencySignal(nextState);
      setRepoStatus(safeMessage);
    } finally {
      setIsRepoBusy(false);
    }
  };

  return {
    repoUrl,
    setRepoUrl,
    repoBranch,
    setRepoBranch,
    repoFiles,
    repoStatus,
    isRepoBusy,
    githubDependencyLifecycle,
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
  };
};
