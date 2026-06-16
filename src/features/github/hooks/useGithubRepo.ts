import { useState } from 'react';
import { RepoFile } from '../types';
import { parseGithubRepoUrl } from '../utils';

export const useGithubRepo = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>([]);
  const [repoStatus, setRepoStatus] = useState('Noch kein echtes Repo geladen.');
  const [isRepoBusy, setIsRepoBusy] = useState(false);

  const restoreRepoSnapshot = (next: {
    repoUrl: string;
    repoBranch: string;
    repoStatus: string;
    repoFiles: RepoFile[];
  }) => {
    setRepoUrl(next.repoUrl);
    setRepoBranch(next.repoBranch);
    setRepoStatus(`${next.repoStatus} [session restored]`);
    setRepoFiles(next.repoFiles.filter((file) => file.type === 'blob' || file.type === 'tree').slice(0, 500));
  };

  const clearRepoSnapshot = () => {
    setRepoFiles([]);
    setRepoStatus('Noch kein echtes Repo geladen.');
  };

  const loadRepoTree = async () => {
    const parsed = parseGithubRepoUrl(repoUrl);

    if (!parsed) {
      setRepoStatus('Ungültige GitHub URL');
      setRepoFiles([]);
      return;
    }

    setIsRepoBusy(true);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);

    try {
      const headers: Record<string, string> = {
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      };

      if (githubToken.trim()) {
        headers.Authorization = `Bearer ${githubToken.trim()}`;
      }

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
      const branchToLoad = repoBranch.trim() || defaultBranch;

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

      setRepoFiles(files);
      setRepoBranch(branchToLoad);
      setRepoStatus(`${files.length} echte Repo-Einträge geladen (${branchToLoad})`);
      console.log(`Repo geladen: ${parsed.owner}/${parsed.repo}`);
    } catch (err) {
      console.error(err);
      setRepoFiles([]);
      setRepoStatus(err instanceof Error ? err.message : 'Fehler beim Laden des Repos');
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
