export const makeId = () => crypto.randomUUID();

/**
 * Redacts sensitive credentials from strings to prevent accidental leakage in logs or UI.
 * Matches common token, key and label-based credential patterns.
 */
export function maskSecrets(text: string): string {
  if (!text) return text;

  let masked = text;

  // GitHub Personal Access Tokens (classic, fine-grained, app and refresh/session variants)
  masked = masked.replace(/(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9_]{8,100}/g, '$1_****');
  masked = masked.replace(/github_pat_[a-zA-Z0-9_]{20,200}/g, 'github_pat_****');

  // Google Cloud / Gemini API keys
  masked = masked.replace(/AIzaSy[a-zA-Z0-9_-]{30,50}/g, 'AIzaSy****');

  // AI provider style keys
  masked = masked.replace(/sk-[a-zA-Z0-9_-]{20,120}/g, 'sk-****');
  masked = masked.replace(/gsk_[a-zA-Z0-9_-]{20,120}/g, 'gsk_****');

  // Generic Bearer tokens in common error messages or strings
  masked = masked.replace(/Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi, 'Bearer ****');

  // Label-based credentials in common logs or error strings (supports optional quotes and base64 characters)
  masked = masked.replace(/(["']?)(password|token|secret|api[_-]?key|access[_-]?token)\1\s*[:=]\s*["']?[a-zA-Z0-9_@#$%^&*.\-~+/=]+["']?/gi, '$2: ****');

  return masked;
}
