import type { ScanFindingRegistry } from './scanFindingRegistry';
import type { LearningMemoryStore } from './sovereignLearningMemory';
import type { SolutionPatternStore } from './solutionPatternMemory';

export type ExternalMemorySyncMode = 'manual' | 'pull-only' | 'push-pull';
export type ExternalMemorySyncItemKind = 'scan-finding' | 'learning-pattern' | 'solution-pattern';
export type ExternalMemorySyncStatus = 'idle' | 'disabled' | 'ready' | 'synced' | 'soft-failed';

export interface ExternalMemorySyncConfig {
  enabled: boolean;
  consentAccepted: boolean;
  gatewayUrl: string;
  workspaceId: string;
  collectionName: string;
  mode: ExternalMemorySyncMode;
  clientAccessKey?: string;
  includeScanFindings: boolean;
  includeLearningPatterns: boolean;
  includeSolutionPatterns: boolean;
}

export interface ExternalMemorySyncValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export interface ExternalMemorySyncItem {
  id: string;
  kind: ExternalMemorySyncItemKind;
  title: string;
  text: string;
  tags: string[];
  metadata: Record<string, string | number | boolean>;
}

export interface ExternalMemorySyncPayload {
  schemaVersion: 1;
  client: 'sovereign-studio';
  workspaceId: string;
  collectionName: string;
  createdAt: number;
  redaction: 'summary-only-no-source-files';
  retrievalProfile: 'hybrid-dense-sparse-graph';
  clientAccessKeyPresent: boolean;
  items: ExternalMemorySyncItem[];
}

export interface ExternalMemorySyncResponse {
  accepted: boolean;
  imported: number;
  exported: number;
  rejected: number;
  summary: string;
  remotePatterns?: ExternalMemorySyncItem[];
}

export interface ExternalMemorySyncResult {
  status: ExternalMemorySyncStatus;
  accepted: boolean;
  payload?: ExternalMemorySyncPayload;
  response?: ExternalMemorySyncResponse;
  validation: ExternalMemorySyncValidationReport;
  summary: string;
}

const MAX_TEXT = 1600;
const MAX_ITEMS = 250;
const SAFE_ID = /^[a-zA-Z0-9._:-]{2,80}$/;
const UNSAFE_TEXT = /(password|credential|private[_-]?key)\s*[:=]\s*\S+/gi;

function sanitizeText(value = ''): string {
  return value.trim().slice(0, MAX_TEXT).replace(UNSAFE_TEXT, '<redacted-sensitive>');
}

function hasUnsafeText(value = ''): boolean {
  UNSAFE_TEXT.lastIndex = 0;
  return UNSAFE_TEXT.test(value);
}

function normalizeTag(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9:_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 48);
}

function normalizeTags(values: string[]): string[] {
  return Array.from(new Set(values.map(normalizeTag).filter(Boolean))).slice(0, 16);
}

function safeUrl(value: string): URL | null {
  try {
    return new URL(value.trim());
  } catch {
    return null;
  }
}

export function createExternalMemorySyncConfig(): ExternalMemorySyncConfig {
  return {
    enabled: false,
    consentAccepted: false,
    gatewayUrl: '',
    workspaceId: 'local-workspace',
    collectionName: 'sovereign_logic_patterns',
    mode: 'manual',
    includeScanFindings: true,
    includeLearningPatterns: true,
    includeSolutionPatterns: true,
  };
}

export function buildExternalMemoryConsentText(): string {
  return [
    'Optional external memory sync is disabled by default.',
    'When enabled, Sovereign Studio sends sanitized logic patterns, finding summaries and repair patterns to the configured Agent Memory gateway.',
    'Raw source files, raw repository contents, private user keys and private credentials are not included by this client-side payload builder.',
    'The gateway may store summaries and metadata in a hybrid retrieval backend such as dense/sparse vector search, keyword search and graph relations.',
    'The user can keep this disabled and use local memory only.',
  ].join('\n');
}

export function validateExternalMemorySyncConfig(config: ExternalMemorySyncConfig): ExternalMemorySyncValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!config.enabled) {
    return { valid: true, errors, warnings: ['External memory sync is disabled.'], summary: 'External memory sync disabled.' };
  }

  if (!config.consentAccepted) errors.push('Consent must be accepted before external memory sync can run.');
  const url = safeUrl(config.gatewayUrl);
  if (!url) errors.push('A valid Agent Memory gateway URL is required.');
  if (url && url.protocol !== 'https:' && url.hostname !== 'localhost' && url.hostname !== '127.0.0.1') {
    errors.push('Gateway URL must use HTTPS unless it is localhost.');
  }
  if (url && url.port === '19530') errors.push('Do not connect the browser directly to a vector database server port. Use the Agent Memory gateway instead.');
  if (!SAFE_ID.test(config.workspaceId)) errors.push('workspaceId must be a safe short identifier.');
  if (!SAFE_ID.test(config.collectionName)) errors.push('collectionName must be a safe short identifier.');
  if (!['manual', 'pull-only', 'push-pull'].includes(config.mode)) errors.push(`Unknown sync mode: ${config.mode}`);
  if (!config.includeScanFindings && !config.includeLearningPatterns && !config.includeSolutionPatterns) warnings.push('No local memory sources are selected for sync.');
  if (config.clientAccessKey && hasUnsafeText(config.clientAccessKey)) warnings.push('Client access key should stay session-only and must not be logged.');

  return { valid: errors.length === 0, errors, warnings, summary: `${errors.length} error(s), ${warnings.length} warning(s) in external memory config.` };
}

export function validateExternalMemorySyncItem(item: ExternalMemorySyncItem): ExternalMemorySyncValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!item.id.trim()) errors.push('Item id is required.');
  if (!['scan-finding', 'learning-pattern', 'solution-pattern'].includes(item.kind)) errors.push(`Unknown item kind: ${item.kind}`);
  if (!item.title.trim()) errors.push('Item title is required.');
  if (!item.text.trim()) errors.push('Item text is required.');
  if (item.text.length > MAX_TEXT) errors.push('Item text is too long.');
  if ([item.id, item.title, item.text, ...item.tags].some(hasUnsafeText)) errors.push('Item contains unsafe raw text.');
  if (!item.tags.length) warnings.push('Item has no tags.');
  return { valid: errors.length === 0, errors, warnings, summary: `${errors.length} error(s), ${warnings.length} warning(s) in external memory item.` };
}

export function validateExternalMemorySyncPayload(payload: ExternalMemorySyncPayload): ExternalMemorySyncValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (payload.schemaVersion !== 1) errors.push('Unsupported payload schemaVersion.');
  if (payload.client !== 'sovereign-studio') errors.push('Unsupported payload client.');
  if (!SAFE_ID.test(payload.workspaceId)) errors.push('Invalid payload workspaceId.');
  if (!SAFE_ID.test(payload.collectionName)) errors.push('Invalid payload collectionName.');
  if (!Number.isFinite(payload.createdAt) || payload.createdAt <= 0) errors.push('Payload createdAt must be positive.');
  if (payload.redaction !== 'summary-only-no-source-files') errors.push('Payload redaction mode must stay summary-only-no-source-files.');
  if (payload.items.length > MAX_ITEMS) errors.push(`Payload exceeds ${MAX_ITEMS} items.`);
  if (!payload.items.length) warnings.push('Payload contains no items.');
  for (const item of payload.items) {
    const itemReport = validateExternalMemorySyncItem(item);
    errors.push(...itemReport.errors.map((error) => `${item.id}: ${error}`));
    warnings.push(...itemReport.warnings.map((warning) => `${item.id}: ${warning}`));
  }
  return { valid: errors.length === 0, errors, warnings, summary: `${payload.items.length} item(s), ${errors.length} error(s), ${warnings.length} warning(s) in external memory payload.` };
}

export function buildExternalMemorySyncPayload(input: {
  config: ExternalMemorySyncConfig;
  scanRegistry?: ScanFindingRegistry;
  learningStore?: LearningMemoryStore;
  solutionStore?: SolutionPatternStore;
  now?: number;
}): ExternalMemorySyncPayload {
  const items: ExternalMemorySyncItem[] = [];
  const now = input.now ?? Date.now();

  if (input.config.includeScanFindings && input.scanRegistry) {
    for (const finding of input.scanRegistry.findings.filter((item) => item.status === 'active').slice(0, 80)) {
      items.push({
        id: `scan-${finding.id}`,
        kind: 'scan-finding',
        title: sanitizeText(finding.title),
        text: sanitizeText(`${finding.category}: ${finding.description} Fix: ${finding.fixTips}`),
        tags: normalizeTags([finding.category, finding.severity, finding.confidence, finding.source]),
        metadata: {
          category: finding.category,
          severity: finding.severity,
          status: finding.status,
          confidence: finding.confidence,
          source: finding.source,
          filePathHint: finding.filePath,
          hits: finding.hits,
        },
      });
    }
  }

  if (input.config.includeLearningPatterns && input.learningStore) {
    for (const pattern of input.learningStore.patterns.slice(0, 80)) {
      items.push({
        id: `learn-${pattern.id}`,
        kind: 'learning-pattern',
        title: sanitizeText(pattern.summary),
        text: sanitizeText(`${pattern.kind}: ${pattern.summary}. Evidence: ${pattern.evidence}`),
        tags: normalizeTags([pattern.kind, pattern.confidence, pattern.sourceNode, ...pattern.outputNodes, ...pattern.tags]),
        metadata: { kind: pattern.kind, confidence: pattern.confidence, sourceNode: pattern.sourceNode, hits: pattern.hits },
      });
    }
  }

  if (input.config.includeSolutionPatterns && input.solutionStore) {
    for (const pattern of input.solutionStore.patterns.filter((item) => item.status === 'active').slice(0, 80)) {
      items.push({
        id: `solve-${pattern.id}`,
        kind: 'solution-pattern',
        title: sanitizeText(pattern.problemSummary),
        text: sanitizeText(`Problem: ${pattern.problemSummary}. Solution: ${pattern.solutionSummary}. Steps: ${pattern.recommendedSteps.join(' | ')}`),
        tags: normalizeTags([pattern.category, pattern.fileExtension, pattern.confidence, ...pattern.conditions, ...pattern.tags]),
        metadata: {
          category: pattern.category,
          fileExtension: pattern.fileExtension,
          confidence: pattern.confidence,
          hits: pattern.hits,
          successfulUses: pattern.successfulUses,
          intakeNode: pattern.intakeNode,
          processingNode: pattern.processingNode,
        },
      });
    }
  }

  const payload = {
    schemaVersion: 1 as const,
    client: 'sovereign-studio' as const,
    workspaceId: input.config.workspaceId,
    collectionName: input.config.collectionName,
    createdAt: now,
    redaction: 'summary-only-no-source-files' as const,
    retrievalProfile: 'hybrid-dense-sparse-graph' as const,
    clientAccessKeyPresent: Boolean(input.config.clientAccessKey),
    items: items.slice(0, MAX_ITEMS),
  };

  const validation = validateExternalMemorySyncPayload(payload);
  if (!validation.valid) throw new Error(`External memory payload is invalid: ${validation.errors.join(' | ')}`);
  return payload;
}

export async function syncExternalMemory(input: {
  config: ExternalMemorySyncConfig;
  payload: ExternalMemorySyncPayload;
  fetcher?: typeof fetch;
}): Promise<ExternalMemorySyncResult> {
  const configReport = validateExternalMemorySyncConfig(input.config);
  const payloadReport = validateExternalMemorySyncPayload(input.payload);
  const validation = {
    valid: configReport.valid && payloadReport.valid,
    errors: [...configReport.errors, ...payloadReport.errors],
    warnings: [...configReport.warnings, ...payloadReport.warnings],
    summary: `${configReport.summary} ${payloadReport.summary}`,
  };

  if (!input.config.enabled) return { status: 'disabled', accepted: false, payload: input.payload, validation, summary: 'External memory sync is disabled.' };
  if (!validation.valid) return { status: 'soft-failed', accepted: false, payload: input.payload, validation, summary: `External memory sync rejected softly: ${validation.summary}` };

  try {
    const fetcher = input.fetcher ?? fetch;
    const endpoint = new URL('/api/sovereign-memory/sync', input.config.gatewayUrl).toString();
    const response = await fetcher(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input.payload, clientAccessKey: input.config.clientAccessKey ? '<session-present>' : undefined }),
    });
    if (!response.ok) return { status: 'soft-failed', accepted: false, payload: input.payload, validation, summary: `External memory gateway returned ${response.status}.` };
    const body = await response.json() as Partial<ExternalMemorySyncResponse>;
    const syncResponse: ExternalMemorySyncResponse = {
      accepted: Boolean(body.accepted),
      imported: Number(body.imported ?? 0),
      exported: Number(body.exported ?? 0),
      rejected: Number(body.rejected ?? 0),
      summary: sanitizeText(body.summary ?? 'External memory sync completed.'),
      remotePatterns: Array.isArray(body.remotePatterns) ? body.remotePatterns.slice(0, 50) : undefined,
    };
    return { status: syncResponse.accepted ? 'synced' : 'soft-failed', accepted: syncResponse.accepted, payload: input.payload, response: syncResponse, validation, summary: syncResponse.summary };
  } catch (error) {
    return { status: 'soft-failed', accepted: false, payload: input.payload, validation, summary: error instanceof Error ? sanitizeText(error.message) : 'External memory sync request failed.' };
  }
}
