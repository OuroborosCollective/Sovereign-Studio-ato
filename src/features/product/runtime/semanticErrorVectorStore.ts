/**
 * Semantic Error Vector Store
 * Lokal ausgeführte Vektor-Embedding für Error-Pattern-Matching
 * Keine LLM-Dependency; nutzt statische Vektoren + Distanzberechnung
 */

export type ErrorFamily =
  | 'GithubAuthError'
  | 'GithubRateLimitError'
  | 'GithubNetworkError'
  | 'ProviderAuthError'
  | 'ProviderServiceError'
  | 'ProviderRateLimitError'
  | 'RepoSnapshotError'
  | 'PackageBuildError'
  | 'FunctionalGuardError'
  | 'WorkflowWatchError'
  | 'UnknownError';

export interface ErrorVector {
  family: ErrorFamily;
  keywords: string[];
  vector: number[]; // Statische Vektoren für locale Semantic Distance
  confidence: number; // 0..1
  repairHint: string;
}

export interface ErrorMatch {
  family: ErrorFamily;
  confidence: number;
  distance: number;
  keywords: string[];
  repairHint: string;
  traceId: string;
}

/**
 * Statische Error-Vektor-Datenbank
 * Basis: Domain-spezifische Keywords + pre-computed normalized vectors
 */
const ERROR_VECTOR_DB: ErrorVector[] = [
  {
    family: 'GithubAuthError',
    keywords: [
      'unauthorized',
      '401',
      'invalid_token',
      'expired_token',
      'bad_credentials',
      'authentication_failed',
      'pat_invalid',
    ],
    vector: [1.0, 0.9, 0.2, 0.1, 0.0, 0.3, 0.8],
    confidence: 0.95,
    repairHint:
      'GitHub PAT invalid oder abgelaufen. Speicher neu in secrets oder env.',
  },
  {
    family: 'GithubRateLimitError',
    keywords: [
      'rate_limit',
      '403',
      'api_rate_limit_exceeded',
      'secondary_rate_limit',
      'too_many_requests',
      'x-ratelimit-remaining: 0',
    ],
    vector: [0.1, 0.8, 0.9, 0.2, 0.1, 0.05, 0.1],
    confidence: 0.92,
    repairHint: 'Rate Limit erreicht. Warte 60s oder nutze GraphQL mit höherem Limit.',
  },
  {
    family: 'GithubNetworkError',
    keywords: [
      'econnrefused',
      'enotfound',
      'timeout',
      'dns',
      'network_error',
      'socket_hang_up',
      'connection_reset',
    ],
    vector: [0.2, 0.1, 0.7, 0.8, 0.6, 0.9, 0.75],
    confidence: 0.88,
    repairHint: 'Netzwerkfehler. Prüfe Internet, Firewall, GitHub-Status.',
  },
  {
    family: 'ProviderAuthError',
    keywords: [
      'api_key_invalid',
      'gemini_auth',
      'provider_unauthorized',
      'invalid_api_key',
      '403_forbidden',
    ],
    vector: [0.95, 0.5, 0.1, 0.2, 0.3],
    confidence: 0.91,
    repairHint: 'Provider API-Key ungültig. Prüfe .env oder Cloudflare Worker Secrets.',
  },
  {
    family: 'ProviderServiceError',
    keywords: [
      'provider_down',
      'service_unavailable',
      '503',
      '500_internal_error',
      'gemini_service_error',
      'temporary_failure',
    ],
    vector: [0.2, 0.3, 0.9, 0.85, 0.1, 0.8],
    confidence: 0.87,
    repairHint: 'Provider-Service offline. Warte 30s oder wechsle zu anderem Provider.',
  },
  {
    family: 'ProviderRateLimitError',
    keywords: [
      'provider_quota_exceeded',
      'tokens_per_minute',
      'requests_per_minute',
      'quota_error',
      'gemini_rate_limit',
    ],
    vector: [0.1, 0.7, 0.9, 0.8, 0.1],
    confidence: 0.89,
    repairHint: 'Provider-Quota überschritten. Nutze andere Session oder warte.',
  },
  {
    family: 'RepoSnapshotError',
    keywords: [
      'repo_not_found',
      '404',
      'invalid_repo_url',
      'snapshot_empty',
      'tree_load_failed',
      'commit_not_found',
    ],
    vector: [0.3, 0.85, 0.2, 0.8, 0.7, 0.6],
    confidence: 0.90,
    repairHint:
      'Repo nicht erreichbar. Prüfe URL, Berechtigung, Public/Private-Status.',
  },
  {
    family: 'PackageBuildError',
    keywords: [
      'file_generation_failed',
      'invalid_output_path',
      'package_build_error',
      'content_validation_failed',
      'schema_mismatch',
    ],
    vector: [0.4, 0.3, 0.9, 0.7, 0.8],
    confidence: 0.86,
    repairHint:
      'Package-Build fehlgeschlagen. Prüfe Provider-Output gegen Sovereign Brain Contract.',
  },
  {
    family: 'FunctionalGuardError',
    keywords: [
      'guard_rejected_output',
      'unsafe_path_detected',
      'secret_in_content',
      'duplicate_file_path',
      'empty_file_content',
    ],
    vector: [0.5, 0.8, 0.95, 0.2, 0.9],
    confidence: 0.93,
    repairHint: 'Funktionale Guard blockierte Output. Prüfe Pfade, Secrets, Duplikate.',
  },
  {
    family: 'WorkflowWatchError',
    keywords: [
      'workflow_not_found',
      'workflow_failed',
      'check_run_failed',
      'ci_check_failed',
      'test_suite_failed',
    ],
    vector: [0.3, 0.7, 0.85, 0.8, 0.9],
    confidence: 0.88,
    repairHint: 'Workflow fehlgeschlagen. Lese Logs, identifiziere failing Job, baue Repair-Mission.',
  },
];

/**
 * Berechne Cosine Distance zwischen zwei Vektoren
 */
function cosineSimilarity(v1: number[], v2: number[]): number {
  const minLen = Math.min(v1.length, v2.length);
  let dotProduct = 0;
  let norm1 = 0;
  let norm2 = 0;

  for (let i = 0; i < minLen; i++) {
    dotProduct += v1[i] * v2[i];
    norm1 += v1[i] * v1[i];
    norm2 += v2[i] * v2[i];
  }

  const denominator = Math.sqrt(norm1 * norm2);
  return denominator === 0 ? 0 : dotProduct / denominator;
}

/**
 * Erstelle einen Error-Query-Vektor aus Error-Message + Stack
 */
function createErrorQueryVector(
  errorMessage: string,
  errorStack?: string,
): number[] {
  const text = `${errorMessage} ${errorStack || ''}`.toLowerCase();

  // Einfache Feature-Extraktion: Präsenz von Keywords
  const features = [
    // Feature 0: Auth-Indikatoren
    text.includes('auth') || text.includes('token') ? 1 : 0,
    // Feature 1: Rate-Limit-Indikatoren
    text.includes('rate') || text.includes('quota') ? 1 : 0,
    // Feature 2: Network-Indikatoren
    text.includes('timeout') ||
    text.includes('econnrefused') ||
    text.includes('enotfound')
      ? 1
      : 0,
    // Feature 3: 404/Not Found
    text.includes('404') || text.includes('not found') ? 1 : 0,
    // Feature 4: 500/Server Error
    text.includes('500') || text.includes('internal error') ? 1 : 0,
    // Feature 5: 403/Forbidden
    text.includes('403') || text.includes('forbidden') ? 1 : 0,
    // Feature 6: Package/Build-bezogen
    text.includes('package') ||
    text.includes('build') ||
    text.includes('generation')
      ? 1
      : 0,
  ];

  return features;
}

/**
 * Sichere Error-Klassifizierung mit Vektor-Distanz
 */
export function classifyErrorFamily(
  errorMessage: string,
  errorStack?: string,
  traceId?: string,
): ErrorMatch {
  const queryVector = createErrorQueryVector(errorMessage, errorStack);
  const lowerMessage = errorMessage.toLowerCase();

  let bestMatch: ErrorMatch = {
    family: 'UnknownError',
    confidence: 0.0,
    distance: 1.0,
    keywords: [],
    repairHint:
      'Unbekannter Fehler. Prüfe Logs, Stack-Trace und Runtime-State.',
    traceId: traceId || generateTraceId(),
  };

  for (const errorVector of ERROR_VECTOR_DB) {
    // Keyword-basierter Pre-Filter
    const hasKeyword = errorVector.keywords.some((kw) =>
      lowerMessage.includes(kw),
    );

    if (!hasKeyword) continue;

    // Vektor-Distanz berechnen
    const similarity = cosineSimilarity(queryVector, errorVector.vector);
    const confidence = Math.max(0, similarity * errorVector.confidence);

    if (confidence > bestMatch.confidence) {
      bestMatch = {
        family: errorVector.family,
        confidence,
        distance: 1 - similarity,
        keywords: errorVector.keywords,
        repairHint: errorVector.repairHint,
        traceId: traceId || generateTraceId(),
      };
    }
  }

  return bestMatch;
}

/**
 * Multi-Match: Alle wahrscheinlichen Fehler-Familien (Top-N)
 */
export function classifyErrorFamiliesTopN(
  errorMessage: string,
  errorStack?: string,
  topN: number = 3,
  traceId?: string,
): ErrorMatch[] {
  const queryVector = createErrorQueryVector(errorMessage, errorStack);
  const lowerMessage = errorMessage.toLowerCase();
  const results: ErrorMatch[] = [];

  for (const errorVector of ERROR_VECTOR_DB) {
    const hasKeyword = errorVector.keywords.some((kw) =>
      lowerMessage.includes(kw),
    );

    if (!hasKeyword) continue;

    const similarity = cosineSimilarity(queryVector, errorVector.vector);
    const confidence = Math.max(0, similarity * errorVector.confidence);

    results.push({
      family: errorVector.family,
      confidence,
      distance: 1 - similarity,
      keywords: errorVector.keywords,
      repairHint: errorVector.repairHint,
      traceId: traceId || generateTraceId(),
    });
  }

  results.sort((a, b) => b.confidence - a.confidence);
  return results.slice(0, topN);
}

/**
 * Generiere Trace-ID für Error-Tracking
 */
function generateTraceId(): string {
  return `err-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Export zur Persistierung oder Monitoring
 */
export function exportVectorStore(): ErrorVector[] {
  return ERROR_VECTOR_DB;
}

export default {
  classifyErrorFamily,
  classifyErrorFamiliesTopN,
  exportVectorStore,
};
