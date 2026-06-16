export const makeId = () => crypto.randomUUID();

/**
 * Redacts sensitive credentials from strings to prevent accidental leakage in logs or UI.
 * Matches common patterns for GitHub tokens, Google API keys, and generic auth tokens.
 */
export function maskSecrets(text: string): string {
  if (!text) return text;

  let masked = text;

  // GitHub Personal Access Tokens (Classic and Fine-grained)
  masked = masked.replace(/ghp_[a-zA-Z0-9]{30,40}/g, 'ghp_****');
  masked = masked.replace(/github_pat_[a-zA-Z0-9]{20,30}_[a-zA-Z0-9]{50,90}/g, 'github_pat_****');

  // Google Cloud API Keys
  masked = masked.replace(/AIzaSy[a-zA-Z0-9_-]{30,40}/g, 'AIzaSy****');

  // Generic Bearer tokens in common error messages or strings
  masked = masked.replace(/Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi, 'Bearer ****');

  return masked;
}
