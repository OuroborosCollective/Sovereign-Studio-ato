export const makeId = () => crypto.randomUUID();

// Hoisted regular expression patterns to avoid redundant recompilation/re-instantiation
// and allocation overhead on every call to maskSecrets.
const GITHUB_PAT_CLASSIC_REGEX = /(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9_]{8,100}/g;
const GITHUB_PAT_FINE_REGEX = /github_pat_[a-zA-Z0-9_]{20,200}/g;
const GEMINI_API_KEY_REGEX = /AIza[a-zA-Z0-9_-]{26,60}/g;
const SK_OR_V1_REGEX = /sk-or-v1-[a-zA-Z0-9_-]{20,}/g;
const SK_PROJ_REGEX = /sk-proj-[a-zA-Z0-9_-]{20,}/g;
const SK_ANT_REGEX = /sk-ant-[a-zA-Z0-9_-]{20,}/g;
const SK_GENERIC_REGEX = /sk-[a-zA-Z0-9_-]{20,}/g;
const GSK_REGEX = /gsk_[a-zA-Z0-9_-]{20,}/g;
const HF_REGEX = /hf_[a-zA-Z0-9]{8,100}/g;
const TOGETHER_REGEX = /together_[a-zA-Z0-9]{8,100}/g;
const POLLINATIONS_REGEX = /pollinations_[a-zA-Z0-9]{8,100}/g;
const BEARER_REGEX = /Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi;
const LABEL_CRED_REGEX = /(["']?)(password|passwd|token|secret|api[_-]?key|access[_-]?token|private[_-]?key)\1(\s*[:=]\s*)["']?[a-zA-Z0-9_@#$%^&*.\-~+/=]+["']?/gi;

// 1-slot memoization to bypass regex processing entirely for identical consecutive log messages or strings.
let lastInput: string | null = null;
let lastOutput: string | null = null;

/**
 * Redacts sensitive credentials from strings to prevent accidental leakage in logs or UI.
 * Matches common token, key and label-based credential patterns.
 */
export function maskSecrets(text: string): string {
  if (!text) return text;

  if (text === lastInput) {
    return lastOutput!;
  }

  let masked = text;

  // GitHub Personal Access Tokens (classic, fine-grained, app and refresh/session variants)
  masked = masked.replace(GITHUB_PAT_CLASSIC_REGEX, '$1_****');
  masked = masked.replace(GITHUB_PAT_FINE_REGEX, 'github_pat_****');

  // Google Cloud / Gemini API keys
  masked = masked.replace(GEMINI_API_KEY_REGEX, 'AIza****');

  // AI provider style keys. Do not cap these matches: long credentials must be consumed up to a delimiter.
  masked = masked.replace(SK_OR_V1_REGEX, 'sk-or-v1-****');
  masked = masked.replace(SK_PROJ_REGEX, 'sk-proj-****');
  masked = masked.replace(SK_ANT_REGEX, 'sk-ant-****');
  masked = masked.replace(SK_GENERIC_REGEX, 'sk-****');
  masked = masked.replace(GSK_REGEX, 'gsk_****');

  // HuggingFace, Together AI and Pollinations AI
  masked = masked.replace(HF_REGEX, 'hf_****');
  masked = masked.replace(TOGETHER_REGEX, 'together_****');
  masked = masked.replace(POLLINATIONS_REGEX, 'pollinations_****');

  // Generic Bearer tokens in common error messages or strings
  masked = masked.replace(BEARER_REGEX, 'Bearer ****');

  // Label-based credentials in common logs or error strings (supports optional quotes and base64 characters)
  masked = masked.replace(LABEL_CRED_REGEX, '$1$2$1$3****');

  lastInput = text;
  lastOutput = masked;
  return masked;
}
