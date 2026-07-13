/**
 * Semantic Error Vector Store
 * Lokal ausgeführte Vektor-Embedding für Error-Pattern-Matching.
 * Der Wahrheitspfad nutzt ausschließlich KappaPos/BigInt-Arithmetik.
 */

import {
  KAPPA_ONE,
  KAPPA_ZERO,
  type KappaPos,
  cosineSimilarityKappa,
  encodeKappaVectorLittleEndian,
  fnv1a64Hex,
  kappaFromDecimalString,
  multiplyKappa,
  sha256Hex,
  subtractKappa,
} from './kappaPos';

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
  keywords: readonly string[];
  vector: readonly KappaPos[];
  confidence: KappaPos;
  repairHint: string;
}

export interface ErrorMatch {
  family: ErrorFamily;
  confidence: KappaPos;
  distance: KappaPos;
  keywords: readonly string[];
  repairHint: string;
  traceId: string;
}

export interface CanonicalErrorVectorRecord {
  family: ErrorFamily;
  payload: Uint8Array;
  fnv1a64: string;
}

const vector = (...values: readonly string[]): readonly KappaPos[] =>
  Object.freeze(values.map(kappaFromDecimalString));

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
    vector: vector('1', '0.9', '0.2', '0.1', '0', '0.3', '0.8'),
    confidence: kappaFromDecimalString('0.95'),
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
    vector: vector('0.1', '0.8', '0.9', '0.2', '0.1', '0.05', '0.1'),
    confidence: kappaFromDecimalString('0.92'),
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
    vector: vector('0.2', '0.1', '0.7', '0.8', '0.6', '0.9', '0.75'),
    confidence: kappaFromDecimalString('0.88'),
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
    vector: vector('0.95', '0.5', '0.1', '0.2', '0.3'),
    confidence: kappaFromDecimalString('0.91'),
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
    vector: vector('0.2', '0.3', '0.9', '0.85', '0.1', '0.8'),
    confidence: kappaFromDecimalString('0.87'),
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
    vector: vector('0.1', '0.7', '0.9', '0.8', '0.1'),
    confidence: kappaFromDecimalString('0.89'),
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
    vector: vector('0.3', '0.85', '0.2', '0.8', '0.7', '0.6'),
    confidence: kappaFromDecimalString('0.90'),
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
    vector: vector('0.4', '0.3', '0.9', '0.7', '0.8'),
    confidence: kappaFromDecimalString('0.86'),
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
    vector: vector('0.5', '0.8', '0.95', '0.2', '0.9'),
    confidence: kappaFromDecimalString('0.93'),
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
    vector: vector('0.3', '0.7', '0.85', '0.8', '0.9'),
    confidence: kappaFromDecimalString('0.88'),
    repairHint: 'Workflow fehlgeschlagen. Lese Logs, identifiziere failing Job, baue Repair-Mission.',
  },
];

function normalizeErrorText(errorMessage: string, errorStack?: string): string {
  return `${errorMessage}\n${errorStack ?? ''}`.toLowerCase();
}

/** Erstelle einen ausschließlich ganzzahligen Error-Query-Vektor. */
function createErrorQueryVector(text: string): readonly KappaPos[] {
  return [
    text.includes('auth') || text.includes('token') ? KAPPA_ONE : KAPPA_ZERO,
    text.includes('rate') || text.includes('quota') ? KAPPA_ONE : KAPPA_ZERO,
    text.includes('timeout') ||
    text.includes('econnrefused') ||
    text.includes('enotfound')
      ? KAPPA_ONE
      : KAPPA_ZERO,
    text.includes('404') || text.includes('not found') ? KAPPA_ONE : KAPPA_ZERO,
    text.includes('500') || text.includes('internal error')
      ? KAPPA_ONE
      : KAPPA_ZERO,
    text.includes('403') || text.includes('forbidden')
      ? KAPPA_ONE
      : KAPPA_ZERO,
    text.includes('package') ||
    text.includes('build') ||
    text.includes('generation')
      ? KAPPA_ONE
      : KAPPA_ZERO,
  ];
}

function resolveTraceId(
  errorMessage: string,
  errorStack: string | undefined,
  traceId: string | undefined,
): string {
  return traceId ?? `err-${fnv1a64Hex(`${errorMessage}\u0000${errorStack ?? ''}`)}`;
}

function hasKeyword(text: string, errorVector: ErrorVector): boolean {
  return errorVector.keywords.some((keyword) => text.includes(keyword));
}

function buildMatch(
  errorVector: ErrorVector,
  queryVector: readonly KappaPos[],
  traceId: string,
): ErrorMatch {
  const similarity = cosineSimilarityKappa(queryVector, errorVector.vector);
  return {
    family: errorVector.family,
    confidence: multiplyKappa(similarity, errorVector.confidence),
    distance: subtractKappa(KAPPA_ONE, similarity),
    keywords: errorVector.keywords,
    repairHint: errorVector.repairHint,
    traceId,
  };
}

/** Sichere Error-Klassifizierung mit deterministischer Kappa-Distanz. */
export function classifyErrorFamily(
  errorMessage: string,
  errorStack?: string,
  traceId?: string,
): ErrorMatch {
  const text = normalizeErrorText(errorMessage, errorStack);
  const queryVector = createErrorQueryVector(text);
  const resolvedTraceId = resolveTraceId(errorMessage, errorStack, traceId);

  let bestMatch: ErrorMatch = {
    family: 'UnknownError',
    confidence: KAPPA_ZERO,
    distance: KAPPA_ONE,
    keywords: [],
    repairHint:
      'Unbekannter Fehler. Prüfe Logs, Stack-Trace und Runtime-State.',
    traceId: resolvedTraceId,
  };

  for (const errorVector of ERROR_VECTOR_DB) {
    if (!hasKeyword(text, errorVector)) continue;

    const candidate = buildMatch(errorVector, queryVector, resolvedTraceId);
    if (candidate.confidence > bestMatch.confidence) {
      bestMatch = candidate;
    }
  }

  return bestMatch;
}

/** Multi-Match: alle wahrscheinlichen Fehlerfamilien in stabiler Reihenfolge. */
export function classifyErrorFamiliesTopN(
  errorMessage: string,
  errorStack?: string,
  topN: number = 3,
  traceId?: string,
): ErrorMatch[] {
  if (!Number.isSafeInteger(topN) || topN < 1) {
    return [];
  }

  const text = normalizeErrorText(errorMessage, errorStack);
  const queryVector = createErrorQueryVector(text);
  const resolvedTraceId = resolveTraceId(errorMessage, errorStack, traceId);
  const results: ErrorMatch[] = [];

  for (const errorVector of ERROR_VECTOR_DB) {
    if (!hasKeyword(text, errorVector)) continue;
    results.push(buildMatch(errorVector, queryVector, resolvedTraceId));
  }

  results.sort((left, right) => {
    if (left.confidence !== right.confidence) {
      return left.confidence > right.confidence ? -1 : 1;
    }
    if (left.family === right.family) return 0;
    return left.family < right.family ? -1 : 1;
  });

  return results.slice(0, topN);
}

function uint32LittleEndian(value: number): Uint8Array {
  if (!Number.isSafeInteger(value) || value < 0 || value > 0xffff_ffff) {
    throw new RangeError(`Ungültiger uint32-Wert: ${value}`);
  }
  const bytes = new Uint8Array(4);
  new DataView(bytes.buffer).setUint32(0, value, true);
  return bytes;
}

function concatBytes(chunks: readonly Uint8Array[]): Uint8Array {
  let totalLength = 0;
  for (const chunk of chunks) totalLength += chunk.byteLength;

  const output = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}

function lengthPrefixedUtf8(value: string): Uint8Array {
  const bytes = new TextEncoder().encode(value);
  return concatBytes([uint32LittleEndian(bytes.byteLength), bytes]);
}

function encodeErrorVectorRecord(errorVector: ErrorVector): Uint8Array {
  const keywordChunks = errorVector.keywords.map(lengthPrefixedUtf8);
  const numericPayload = encodeKappaVectorLittleEndian([
    errorVector.confidence,
    ...errorVector.vector,
  ]);

  return concatBytes([
    lengthPrefixedUtf8(errorVector.family),
    uint32LittleEndian(errorVector.keywords.length),
    ...keywordChunks,
    lengthPrefixedUtf8(errorVector.repairHint),
    uint32LittleEndian(numericPayload.byteLength),
    numericPayload,
  ]);
}

/** Kanonische, Little-Endian-fähige Datensätze für SQLite/R2. */
export function exportVectorStoreBinary(): CanonicalErrorVectorRecord[] {
  return ERROR_VECTOR_DB.map((errorVector) => {
    const payload = encodeErrorVectorRecord(errorVector);
    return {
      family: errorVector.family,
      payload,
      fnv1a64: fnv1a64Hex(payload),
    };
  });
}

/** Plattformübergreifender SHA-256 über den vollständigen kanonischen Store. */
export async function hashVectorStoreSha256(): Promise<string> {
  const records = exportVectorStoreBinary();
  const payload = concatBytes([
    uint32LittleEndian(records.length),
    ...records.flatMap((record) => [
      uint32LittleEndian(record.payload.byteLength),
      record.payload,
    ]),
  ]);
  return sha256Hex(payload);
}

/** Export als unverknüpfte Kopie; interne Wahrheit bleibt unveränderlich. */
export function exportVectorStore(): ErrorVector[] {
  return ERROR_VECTOR_DB.map((errorVector) => ({
    ...errorVector,
    keywords: [...errorVector.keywords],
    vector: [...errorVector.vector],
  }));
}

export default {
  classifyErrorFamily,
  classifyErrorFamiliesTopN,
  exportVectorStore,
  exportVectorStoreBinary,
  hashVectorStoreSha256,
};
