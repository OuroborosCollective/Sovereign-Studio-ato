import { ParsedRepo } from './types';

export const parseGithubRepoUrl = (value: string): ParsedRepo | null => {
  const match = value.trim().match(/github\.com\/([^/?#]+)\/([^/?#]+?)(?:\.git)?\/?(?:[?#].*)?$/i);
  if (!match) return null;
  return {
    owner: decodeURIComponent(match[1]),
    repo: decodeURIComponent(match[2].replace(/\.git$/i, '')),
  };
};
