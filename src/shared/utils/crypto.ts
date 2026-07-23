export const makeId = () => crypto.randomUUID();

// Hoisted regular expressions to module-level scope to avoid redundant compilation
// and instantiation overhead on every call to maskSecrets.
const GITHUB_PAT_CLASSIC_REGEX = /(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9_]{8,100}/g;
const GITHUB_PAT_FINE_GRAINED_REGEX = /github_pat_[a-zA-Z0-9_]{20,200}/g;
const GEMINI_API_KEY_REGEX = /AIza[a-zA-Z0-9_-]{26,60}/g;
const OPENAI_OR_V1_REGEX = /sk-or-v1-[a-zA-Z0-9_-]{20,}/g;
const OPENAI_PROJ_REGEX = /sk-proj-[a-zA-Z0-9_-]{20,}/g;
const ANTHROPIC_KEY_REGEX = /sk-ant-[a-zA-Z0-9_-]{20,}/g;
const OPENAI_KEY_REGEX = /sk-[a-zA-Z0-9_-]{20,}/g;
const GROQ_KEY_REGEX = /gsk_[a-zA-Z0-9_-]{20,}/g;
const HUGGINGFACE_KEY_REGEX = /hf_[a-zA-Z0-9]{8,100}/g;
const TOGETHER_KEY_REGEX = /together_[a-zA-Z0-9]{8,100}/g;
const POLLINATIONS_KEY_REGEX = /pollinations_[a-zA-Z0-9]{8,100}/g;
const BEARER_TOKEN_REGEX = /Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi;
const LABEL_CREDENTIAL_REGEX = /(["']?)(password|passwd|token|secret|api[_-]?key|access[_-]?token|private[_-]?key)\1(\s*[:=]\s*)["']?[a-zA-Z0-9_@#$%^&*.\-~+/=]+["']?/gi;

// 1-slot memoization cache to optimize consecutive calls with identical text
// (extremely common during high-frequency chat pacing or parent re-renders).
let lastMaskInput: string | null = null;
let lastMaskOutput: string | null = null;

/**
 * Redacts sensitive credentials from strings to prevent accidental leakage in logs or UI.
 * Matches common token, key and label-based credential patterns.
 */
export function maskSecrets(text: string): string {
  if (!text) return text;

  // O(1) Cache bypass for identical consecutive strings
  if (text === lastMaskInput && lastMaskOutput !== null) {
    return lastMaskOutput;
  }

  let masked = text;

  // GitHub Personal Access Tokens (classic, fine-grained, app and refresh/session variants)
  masked = masked.replace(GITHUB_PAT_CLASSIC_REGEX, '$1_****');
  masked = masked.replace(GITHUB_PAT_FINE_GRAINED_REGEX, 'github_pat_****');

  // Google Cloud / Gemini API keys
  masked = masked.replace(GEMINI_API_KEY_REGEX, 'AIza****');

  // AI provider style keys. Do not cap these matches: long credentials must be consumed up to a delimiter.
  masked = masked.replace(OPENAI_OR_V1_REGEX, 'sk-or-v1-****');
  masked = masked.replace(OPENAI_PROJ_REGEX, 'sk-proj-****');
  masked = masked.replace(ANTHROPIC_KEY_REGEX, 'sk-ant-****');
  masked = masked.replace(OPENAI_KEY_REGEX, 'sk-****');
  masked = masked.replace(GROQ_KEY_REGEX, 'gsk_****');

  // HuggingFace, Together AI and Pollinations AI
  masked = masked.replace(HUGGINGFACE_KEY_REGEX, 'hf_****');
  masked = masked.replace(TOGETHER_KEY_REGEX, 'together_****');
  masked = masked.replace(POLLINATIONS_KEY_REGEX, 'pollinations_****');

  // Generic Bearer tokens in common error messages or strings
  masked = masked.replace(BEARER_TOKEN_REGEX, 'Bearer ****');

  // Label-based credentials in common logs or error strings (supports optional quotes and base64 characters)
  masked = masked.replace(LABEL_CREDENTIAL_REGEX, '$1$2$1$3****');

  // Update the 1-slot cache
  lastMaskInput = text;
  lastMaskOutput = masked;

  return masked;
}
