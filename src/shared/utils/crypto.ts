export const makeId = () => crypto.randomUUID();

/**
 * Redacts sensitive credentials from strings to prevent accidental leakage in logs or UI.
 * Matches common token, key and label-based credential patterns.
 */
export function maskSecrets(text: string): string {
  if (!text) return text;

  let masked = text;

  // GitHub Personal Access Tokens (classic, fine-grained, app and refresh/session variants)
  masked = masked.replace(/(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{30,100}/g, '$1_****');
  masked = masked.replace(/github_pat_[a-zA-Z0-9_.]{22,200}/g, 'github_pat_****');

  // Google Cloud / Gemini API keys
  masked = masked.replace(/(AIzaSy)[a-zA-Z0-9_-]{20,60}/g, '$1****');
  masked = masked.replace(/AIza[a-zA-Z0-9_-]{30,60}/g, 'AIza****');

  // AI provider style keys
  masked = masked.replace(/sk-[a-zA-Z0-9_-]{20,120}/g, 'sk-****');
  masked = masked.replace(/gsk_[a-zA-Z0-9_-]{20,120}/g, 'gsk_****');

  // Authorization headers and Generic Bearer tokens
  masked = masked.replace(/(authorization\s*[:=]\s*Bearer\s+)[a-zA-Z0-9._~+/-]{15,120}=*/gi, '$1****');
  masked = masked.replace(/(authorization\s*[:=]\s*)(?!Bearer\s+)[a-zA-Z0-9_+\-./= ]{15,}/gi, '$1****');
  masked = masked.replace(/Bearer\s+[a-zA-Z0-9._~+/-]{15,120}=*/gi, 'Bearer ****');

  // Label-based credentials in common logs or error strings (supporting quotes)
  masked = masked.replace(
    /(["']?(?:password|token|secret|api[_-]?key|access[_-]?token|passwd|pwd)["']?\s*[:=]\s*["']?)[a-zA-Z0-9_@#$%^&*.\-~+/=]{8,120}/gi,
    '$1****',
  );

  return masked;
}
