import { useState } from 'react';
import {
  clearDurableRepoSnapshot,
  createDurableRepoSnapshot,
  loadDurableRepoSnapshot,
  saveDurableRepoSnapshot,
  type DurableRepoSnapshot,
} from '../repoSnapshotPersistence';
import { buildGitHubHeaders, stripTokenFromText } from '../githubAuthSession';
import { RepoFile } from '../types';
import { parseGithubRepoUrl } from '../utils';

export interface LoadRepoTreeOptions {
  repoUrl?: string;
  repoBranch?: string;
  githubToken?: string;
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
  const [githubToken, setGithubToken] = useState('');
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>(initialSnapshot?.repoFiles ?? []);
  const [repoStatus, setRepoStatus] = useState(initialSnapshot ? `${initialSnapshot.repoStatus} [durable restored]` : 'Noch kein echtes Repo geladen.');
  const [isRepoBusy, setIsRepoBusy] = useState(false);

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
    persistSnapshot({ repoUrl: next.repoUrl, repoBranch: next.repoBranch, repoStatus: nextStatus, repoFiles: safeFiles });
  };

  const clearRepoSnapshot = () => {
    setRepoFiles([]);
    setRepoStatus('Noch kein echtes Repo geladen.');
    if (typeof window !== 'undefined') clearDurableRepoSnapshot(window.localStorage);
  };

  const loadRepoTree = async (options: LoadRepoTreeOptions = {}) => {
    const nextRepoUrl = (options.repoUrl ?? repoUrl).trim();
    const nextRepoBranch = (options.repoBranch ?? repoBranch).trim();
    const nextGithubToken = options.githubToken ?? githubToken;

    if (options.repoUrl !== undefined) setRepoUrl(nextRepoUrl);
    if (options.repoBranch !== undefined) setRepoBranch(nextRepoBranch);
    if (options.githubToken !== undefined) setGithubToken(nextGithubToken);

    const parsed = parseGithubRepoUrl(nextRepoUrl);

    if (!parsed) {
      setRepoStatus('Ungültige GitHub URL');
      setRepoFiles([]);
      return;
    }

    setIsRepoBusy(true);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);

    try {
      const headers = buildGitHubHeaders({ token: nextGithubToken });

      const repoResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}`,
        { headers }
      );

      if (!repoResponse.ok) {
        if (repoResponse.status === 401 || repoResponse.status === 403) {
          throw new Error('GitHub Token fehlt, ist abgelaufen oder hat keine Repo-Berechtigung.');
        }
        if (repoResponse.status === 404) {
          throw new Error('Repository nicht gefunden oder für diesen Token nicht sichtbar.');
        }
        throw new Error(`GitHub Repo-Info Fehler: ${repoResponse.status}`);
      }

      const repoData = await repoResponse.json();
      const defaultBranch = typeof repoData.default_branch === 'string' && repoData.default_branch.trim()
        ? repoData.default_branch.trim()
        : 'main';
      const branchToLoad = nextRepoBranch || defaultBranch;

      let response = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${encodeURIComponent(branchToLoad)}?recursive=1`,
        { headers }
      );

      if (!response.ok && response.status === 404 && branchToLoad !== defaultBranch) {
        setRepoStatus(`Branch '${branchToLoad}' nicht gefunden. Nutze Default-Branch '${defaultBranch}'...`);
        response = await fetch(
          `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${encodeURIComponent(defaultBranch)}?recursive=1`,
          { headers }
        );
      }

      if (!response.ok) {
        throw new Error(`GitHub Tree Fehler: ${response.status}`);
      }

      const data = await response.json();
      const treeData = Array.isArray(data.tree) ? data.tree : [];
      const files: RepoFile[] = [];

      for (let i = 0; i < treeData.length; i++) {
        const f = treeData[i];
        if (f.type === 'blob' || f.type === 'tree') {
          files.push({
            path: f.path,
            type: f.type,
            size: f.size,
          });
          if (files.length === 500) {
            break;
          }
        }
      }

      const nextStatus = `${files.length} echte Repo-Einträge geladen (${branchToLoad})`;
      setRepoFiles(files);
      setRepoBranch(branchToLoad);
      setRepoStatus(nextStatus);
      persistSnapshot({ repoUrl: nextRepoUrl, repoBranch: branchToLoad, repoStatus: nextStatus, repoFiles: files });
      console.log(`Repo geladen: ${parsed.owner}/${parsed.repo}`);
    } catch (err) {
      console.error(err);
      setRepoFiles([]);
      const message = err instanceof Error ? err.message : 'Fehler beim Laden des Repos';
      setRepoStatus(stripTokenFromText(message, nextGithubToken));
    } finally {
      setIsRepoBusy(false);
    }
  };

  return {
    repoUrl,
    setRepoUrl,
    repoBranch,
    setRepoBranch,
    githubToken,
    setGithubToken,
    repoFiles,
    repoStatus,
    isRepoBusy,
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
  };
};
