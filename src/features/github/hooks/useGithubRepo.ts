import { useState } from 'react';
import { RepoFile } from '../types';
import { parseGithubRepoUrl } from '../utils';

const sampleRepoFiles: RepoFile[] = [
  { path: '.github/workflows/ci.yml', type: 'blob' },
  { path: 'package.json', type: 'blob' },
  { path: 'src/App.tsx', type: 'blob' },
];

export const useGithubRepo = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('main');
  const [githubToken, setGithubToken] = useState('');
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>(sampleRepoFiles);
  const [repoStatus, setRepoStatus] = useState('');
  const [isRepoBusy, setIsRepoBusy] = useState(false);

  const loadRepoTree = async () => {
    const parsed = parseGithubRepoUrl(repoUrl);

    if (!parsed) {
      setRepoStatus('Ungültige GitHub URL');
      return;
    }

    setIsRepoBusy(true);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);

    try {
      const headers: Record<string, string> = {
        Accept: 'application/vnd.github+json',
      };

      if (githubToken.trim()) {
        headers.Authorization = `Bearer ${githubToken.trim()}`;
      }

      const response = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${repoBranch}?recursive=1`,
        { headers }
      );

      if (!response.ok) {
        throw new Error(`GitHub API Fehler: ${response.status}`);
      }

      const data = await response.json();

      const treeData = data.tree ?? [];
      const files: RepoFile[] = [];

      for (let i = 0; i < treeData.length; i++) {
        const f = treeData[i];
        if (f.type === 'blob' || f.type === 'tree') {
          files.push({
            path: f.path,
            type: f.type,
            size: f.size,
          });
          if (files.length === 250) {
            break;
          }
        }
      }

      setRepoFiles(files);
      setRepoStatus(`${files.length} Dateien geladen`);
      console.log(`Repo geladen: ${parsed.owner}/${parsed.repo}`);
    } catch (err) {
      console.error(err);
      setRepoStatus('Fehler beim Laden des Repos');
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
  };
};
