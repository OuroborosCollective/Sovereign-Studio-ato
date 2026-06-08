import { ParsedRepo } from './types';

export const parseGithubRepoUrl = (value: string): ParsedRepo | null => {
  const match = value.match(/github\.com\/([^/]+)\/([^/]+)/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace('.git', '') };
};
