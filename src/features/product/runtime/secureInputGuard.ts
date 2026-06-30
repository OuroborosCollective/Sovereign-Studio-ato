/**
 * secureInputGuard - Detects secrets/tokens in normal chat input and blocks them.
 *
 * Rule: Token/PAT must NEVER land in chat history, logs, telemetry,
 * worker prompts, pattern memory, or the repo.
 *
 * The guard fires before the message reaches any storage or LLM path.
 */

export type SecretKind =
  | 'github_pat'
  | 'github_pat_fine'
  | 'openai_key'
  | 'anthropic_key'
  | 'generic_bearer'
  | 'generic_secret';

export interface SecretDetection {
  readonly detected: true;
  readonly kind: SecretKind;
  readonly hint: string;
}

export interface NoSecretDetected {
  readonly detected: false;
}

export type SecretGuardResult = SecretDetection | NoSecretDetected;

const SECRET_PATTERNS: Array<{ readonly kind: SecretKind; readonly pattern: RegExp }> = [
  { kind: 'github_pat', pattern: /\bghp_[A-Za-z0-9]{20,}\b/ },
  { kind: 'github_pat_fine', pattern: /\bgithub_pat_[A-Za-z0-9_]{20,}\b/ },
  { kind: 'openai_key', pattern: /\bsk-[A-Za-z0-9]{20,}\b/ },
  { kind: 'anthropic_key', pattern: /\bsk-ant-[A-Za-z0-9_-]{20,}\b/ },
  { kind: 'generic_bearer', pattern: /\bBearer\s+[A-Za-z0-9\-._~+/]{20,}\b/i },
  {
    kind: 'generic_secret',
    pattern: /\b(?:token|secret|password|passwd|api[_-]?key)\s*[:=]\s*[A-Za-z0-9\-._~+/]{10,}/i,
  },
];

const HINT_FOR_KIND: Record<SecretKind, string> = {
  github_pat: 'GitHub Personal Access Token (ghp_…)',
  github_pat_fine: 'GitHub Fine-Grained PAT (github_pat_…)',
  openai_key: 'OpenAI API Key (sk-…)',
  anthropic_key: 'Anthropic API Key (sk-ant-…)',
  generic_bearer: 'Bearer Token',
  generic_secret: 'Secret / Token / API Key',
};

export function scanForSecret(input: string): SecretGuardResult {
  const trimmed = input.trim();
  if (trimmed.length < 10) return { detected: false };

  for (const entry of SECRET_PATTERNS) {
    if (entry.pattern.test(trimmed)) {
      return {
        detected: true,
        kind: entry.kind,
        hint: HINT_FOR_KIND[entry.kind],
      };
    }
  }

  return { detected: false };
}

export function redactSecret(input: string): string {
  let redacted = input;
  for (const entry of SECRET_PATTERNS) {
    redacted = redacted.replace(entry.pattern, '[REDACTED]');
  }
  return redacted;
}

export interface SecureInputPolicy {
  readonly shouldBlock: boolean;
  readonly kind: SecretKind | null;
  readonly userMessage: string;
  readonly actionLabel: string;
}

export function evaluateInputPolicy(input: string): SecureInputPolicy {
  const result = scanForSecret(input);
  if (!result.detected) {
    return {
      shouldBlock: false,
      kind: null,
      userMessage: '',
      actionLabel: '',
    };
  }
  return {
    shouldBlock: true,
    kind: result.kind,
    userMessage: `Sicherer Zugang erkannt. Diese Eingabe wurde nicht als Chat gespeichert. Bitte nutze das sicheres Zugangsfeld.`,
    actionLabel: 'PAT sicher eingeben',
  };
}
