export function canWriteToGitHub(token: string, path: string, content: string): boolean {
  return token.trim().length > 10 && path.trim().length > 0 && content.trim().length > 0;
}

export function explainWriteGuard(token: string, path: string, content: string): string {
  if (!token.trim()) return 'missing-token';
  if (!path.trim()) return 'missing-path';
  if (!content.trim()) return 'missing-content';
  return 'ready';
}
