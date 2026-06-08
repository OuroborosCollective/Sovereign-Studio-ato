export interface RepoFile {
  path: string;
  type: 'blob' | 'tree';
  size?: number;
}

export interface ParsedRepo {
  owner: string;
  repo: string;
}
