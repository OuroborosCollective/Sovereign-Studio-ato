import type { ScanFindingRegistry } from './scanFindingRegistry';
import type { LearningMemoryStore } from './sovereignLearningMemory';
import type { SolutionPatternStore } from './solutionPatternMemory';

export type ExternalMemorySyncMode = 'manual' | 'pull-only' | 'push-pull';
export type ExternalMemorySyncItemKind = 'scan-finding' | 'learning-pattern' | 'solution-pattern';
export type ExternalMemorySyncStatus = 'idle' | 'disabled' | 'ready' | 'synced' | 'soft-failed';
export type ExternalMemoryContributionScope = 'user-submitted-summary' | 'shared-derived-pattern';
export type ExternalMemoryErasureScope = 'contributor-submissions';

export const EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT = 'DELETE_REMOTE_MEMORY' as const;

export interface ExternalMemorySyncConfig {
  enabled: boolean;
  consentAccepted: boolean;
  gatewayUrl: string;
  workspaceId: string;
  collectionName: string;
  contributorId: string;
  mode: ExternalMemorySyncMode;
  clientAccessKey?: string;
  allowSelfHostedHttp?: boolean;
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
  contributorId: string;
  contributionScope: 'user-submitted-summary';
  createdAt: number;
  redaction: 'summary-only-no-source-files';
  retrievalProfile: 'hybrid-dense-sparse-graph';
  clientAccessKeyPresent: boolean;
  items: ExternalMemorySyncItem[];
}

export interface ExternalMemorySyncResponse {
  accepted: boolean;
  success: boolean;
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

export interface ExternalMemoryHealthResult {
  status: ExternalMemorySyncStatus;
  ok: boolean;
  summary: string;
  details?: Record<string, unknown>;
  validation: ExternalMemorySyncValidationReport;
}

export interface ExternalMemorySearchQuery {
  schemaVersion: 1;
  client: 'sovereign-studio';
  redaction: 'summary-only-no-source-files';
  workspaceId: string;
  collectionName: string;
  contributorId: string;
  includeSharedPatterns: true;
  query: string;
  limit: number;
}

export interface ExternalMemorySearchResult {
  status: ExternalMemorySyncStatus;
  ok: boolean;
  query: ExternalMemorySearchQuery;
  items: ExternalMemorySyncItem[];
  summary: string;
  validation: ExternalMemorySyncValidationReport;
}

export interface ExternalMemoryPullUpdatesResult {
  status: ExternalMemorySyncStatus;
  ok: boolean;
  items: ExternalMemorySyncItem[];
  summary: string;
  validation: ExternalMemorySyncValidationReport;
}

export interface ExternalMemoryDeleteRequest {
  schemaVersion: 1;
  client: 'sovereign-studio';
  redaction: 'summary-only-no-source-files';
  workspaceId: string;
  collectionName: string;
  contributorId: string;
  requestedAt: number;
  confirmDelete: true;
  confirmationText: typeof EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT;
  scope: ExternalMemoryErasureScope;
  preserveSharedPatterns: true;
}

export interface ExternalMemoryDeleteResponse {
  success: boolean;
  deleted: boolean;
  deletedItems: number;
  retainedSharedItems: number;
  summary: string;
}

export interface ExternalMemoryDeleteResult {
  status: ExternalMemorySyncStatus;
  deleted: boolean;
  request?: ExternalMemoryDeleteRequest;
  response?: ExternalMemoryDeleteResponse;
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

function buildGatewayEndpoint(config: ExternalMemorySyncConfig, path: string): string {
  const base = safeUrl(config.gatewayUrl);
  if (!base) throw new Error('Invalid gateway URL.');
  return new URL(path, base).toString();
}

function buildGatewayHeaders(config: ExternalMemorySyncConfig): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    ...(config.clientAccessKey ? { 'X-Sovereign-Gateway-Key': config.clientAccessKey } : {}),
  };
}

function parseRemoteItems(value: unknown): ExternalMemorySyncItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Partial<ExternalMemorySyncItem> => Boolean(item) && typeof item === 'object')
    .map((item, index): ExternalMemorySyncItem => ({
      id: sanitizeText(String(item.id ?? `remote-${index}`)),
      kind: ['scan-finding', 'learning-pattern', 'solution-pattern'].includes(String(item.kind))
        ? item.kind as ExternalMemorySyncItemKind
        : 'solution-pattern',
      title: sanitizeText(String(item.title ?? 'Remote pattern')),
      text: sanitizeText(String(item.text ?? item.title ?? 'Remote pattern')),
      tags: normalizeTags(Array.isArray(item.tags) ? item.tags.map(String) : ['remote']),
      metadata: typeof item.metadata === 'object' && item.metadata ? item.metadata as ExternalMemorySyncItem['metadata'] : {},
    }))
    .filter((item) => validateExternalMemorySyncItem(item).valid)
    .slice(0, 50);
}

export function createExternalMemorySyncConfig(): ExternalMemorySyncConfig {
  return {
    enabled: false,
    consentAccepted: false,
    gatewayUrl: '',
    workspaceId: 'local-workspace',
    collectionName: 'sovereign_logic_patterns',
    contributorId: 'local-contributor',
    mode: 'manual',
    allowSelfHostedHttp: false,
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
    'User-submitted summaries are tagged with a contributor id so erasure requests can target only that contributor’s submissions.',
    'Shared derived pattern updates are not removed by a contributor erasure request.',
    'The user can keep this disabled and use local memory only.',
  ].join('\n');
}

export function buildExternalMemoryDeleteWarningText(): string {
  return [
    'Achtung: Diese Aktion fordert die Entfernung deiner zuvor übermittelten Remote-Memory-Beiträge an.',
    'Betroffen sind nur contributor-submissions für den konfigurierten Contributor, Workspace und die Collection.',
    'Gemeinsame, abgeleitete Pattern-Updates bleiben erhalten und werden nicht durch diesen Request entfernt.',
    'Lokale Session-Daten im Browser werden dadurch nicht automatisch entfernt.',
    `Zur Bestätigung muss ${EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT} bestätigt werden.`,
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
  const localHost = url?.hostname === 'localhost' || url?.hostname === '127.0.0.1';
  const selfHostedHttp = url?.protocol === 'http:' && Boolean(config.allowSelfHostedHttp);
  if (url && url.protocol !== 'https:' && !localHost && !selfHostedHttp) errors.push('Gateway URL must use HTTPS unless self-hosted HTTP testing is explicitly enabled.');
  if (selfHostedHttp) warnings.push('Self-hosted HTTP is allowed for testing. Use HTTPS before production use.');
  if (url && url.port === '19530') errors.push('Do not connect the browser directly to a vector database server port. Use the Agent Memory gateway instead.');
  if (!SAFE_ID.test(config.workspaceId)) errors.push('workspaceId must be a safe short identifier.');
  if (!SAFE_ID.test(config.collectionName)) errors.push('collectionName must be a safe short identifier.');
  if (!SAFE_ID.test(config.contributorId)) errors.push('contributorId must be a safe short identifier.');
  if (config.contributorId === 'local-contributor') warnings.push('Default contributorId is intended for local testing. Use a stable per-installation id before production sync.');
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
  if (item.metadata.contributionScope && item.metadata.contributionScope !== 'user-submitted-summary' && item.metadata.contributionScope !== 'shared-derived-pattern') {
    errors.push('Item contributionScope is invalid.');
  }
  return { valid: errors.length === 0, errors, warnings, summary: `${errors.length} error(s), ${warnings.length} warning(s) in external memory item.` };
}

export function validateExternalMemorySyncPayload(payload: ExternalMemorySyncPayload): ExternalMemorySyncValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (payload.schemaVersion !== 1) errors.push('Unsupported payload schemaVersion.');
  if (payload.client !== 'sovereign-studio') errors.push('Unsupported payload client.');
  if (!SAFE_ID.test(payload.workspaceId)) errors.push('Invalid payload workspaceId.');
  if (!SAFE_ID.test(payload.collectionName)) errors.push('Invalid payload collectionName.');
  if (!SAFE_ID.test(payload.contributorId)) errors.push('Invalid payload contributorId.');
  if (payload.contributionScope !== 'user-submitted-summary') errors.push('Payload contributionScope must be user-submitted-summary.');
  if (!Number.isFinite(payload.createdAt) || payload.createdAt <= 0) errors.push('Payload createdAt must be positive.');
  if (payload.redaction !== 'summary-only-no-source-files') errors.push('Payload redaction mode must stay summary-only-no-source-files.');
  if (payload.items.length > MAX_ITEMS) errors.push(`Payload exceeds ${MAX_ITEMS} items.`);
  if (!payload.items.length) warnings.push('Payload contains no items.');
  for (const item of payload.items) {
    const itemReport = validateExternalMemorySyncItem(item);
    errors.push(...itemReport.errors.map((error) => `${item.id}: ${error}`));
    warnings.push(...itemReport.warnings.map((warning) => `${item.id}: ${warning}`));
    if (item.metadata.contributorId !== payload.contributorId) errors.push(`${item.id}: item contributorId does not match payload contributorId.`);
    if (item.metadata.contributionScope !== payload.contributionScope) errors.push(`${item.id}: item contributionScope does not match payload contributionScope.`);
  }
  return { valid: errors.length === 0, errors, warnings, summary: `${payload.items.length} item(s), ${errors.length} error(s), ${warnings.length} warning(s) in external memory payload.` };
}

function contributorMetadata(config: ExternalMemorySyncConfig): Record<string, string> {
  return {
    contributorId: config.contributorId,
    contributionScope: 'user-submitted-summary',
  };
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
  const contributor = contributorMetadata(input.config);

  if (input.config.includeScanFindings && input.scanRegistry) {
    for (const finding of input.scanRegistry.findings.filter((item) => item.status === 'active').slice(0, 80)) {
      items.push({
        id: `scan-${finding.id}`,
        kind: 'scan-finding',
        title: sanitizeText(finding.title),
        text: sanitizeText(`${finding.category}: ${finding.description} Fix: ${finding.fixTips}`),
        tags: normalizeTags([finding.category, finding.severity, finding.confidence, finding.source]),
        metadata: {
          ...contributor,
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
        metadata: { ...contributor, kind: pattern.kind, confidence: pattern.confidence, sourceNode: pattern.sourceNode, hits: pattern.hits },
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
          ...contributor,
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
    contributorId: input.config.contributorId,
    contributionScope: 'user-submitted-summary' as const,
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

export function buildExternalMemoryDeleteRequest(config: ExternalMemorySyncConfig, now = Date.now()): ExternalMemoryDeleteRequest {
  const request = {
    schemaVersion: 1 as const,
    client: 'sovereign-studio' as const,
    redaction: 'summary-only-no-source-files' as const,
    workspaceId: config.workspaceId,
    collectionName: config.collectionName,
    contributorId: config.contributorId,
    requestedAt: now,
    confirmDelete: true as const,
    confirmationText: EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT,
    scope: 'contributor-submissions' as const,
    preserveSharedPatterns: true as const,
  };
  const validation = validateExternalMemoryDeleteRequest(request);
  if (!validation.valid) throw new Error(`External memory delete request is invalid: ${validation.errors.join(' | ')}`);
  return request;
}

export function validateExternalMemoryDeleteRequest(request: ExternalMemoryDeleteRequest): ExternalMemorySyncValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (request.schemaVersion !== 1) errors.push('Unsupported delete request schemaVersion.');
  if (request.client !== 'sovereign-studio') errors.push('Unsupported delete request client.');
  if (request.redaction !== 'summary-only-no-source-files') errors.push('Delete request redaction must stay summary-only-no-source-files.');
  if (!SAFE_ID.test(request.workspaceId)) errors.push('Invalid delete request workspaceId.');
  if (!SAFE_ID.test(request.collectionName)) errors.push('Invalid delete request collectionName.');
  if (!SAFE_ID.test(request.contributorId)) errors.push('Invalid delete request contributorId.');
  if (!Number.isFinite(request.requestedAt) || request.requestedAt <= 0) errors.push('Delete request timestamp must be positive.');
  if (request.confirmDelete !== true) errors.push('Delete request must include confirmDelete=true.');
  if (request.confirmationText !== EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT) errors.push('Delete request confirmation text is invalid.');
  if (request.scope !== 'contributor-submissions') errors.push('Delete request scope must be contributor-submissions.');
  if (request.preserveSharedPatterns !== true) errors.push('Delete request must preserve shared patterns.');
  if (request.contributorId === 'local-contributor') warnings.push('Default contributorId is intended for local testing. Confirm this is intended.');
  return { valid: errors.length === 0, errors, warnings, summary: `${errors.length} error(s), ${warnings.length} warning(s) in external memory delete request.` };
}

function emptyValidation(summary: string): ExternalMemorySyncValidationReport {
  return { valid: true, errors: [], warnings: [], summary };
}

export async function checkExternalMemoryHealth(input: {
  config: ExternalMemorySyncConfig;
  fetcher?: typeof fetch;
}): Promise<ExternalMemoryHealthResult> {
  const validation = validateExternalMemorySyncConfig(input.config);
  if (!input.config.enabled) return { status: 'disabled', ok: false, validation, summary: 'External memory sync is disabled.' };
  if (!validation.valid) return { status: 'soft-failed', ok: false, validation, summary: validation.summary };
  try {
    const response = await (input.fetcher ?? fetch)(buildGatewayEndpoint(input.config, '/health'), { headers: buildGatewayHeaders(input.config) });
    const body = await response.json().catch(() => ({})) as Record<string, unknown>;
    return { status: response.ok ? 'ready' : 'soft-failed', ok: response.ok, validation, details: body, summary: response.ok ? 'External memory gateway is reachable.' : `External memory gateway returned ${response.status}.` };
  } catch (error) {
    return { status: 'soft-failed', ok: false, validation, summary: error instanceof Error ? sanitizeText(error.message) : 'External memory health request failed.' };
  }
}

export async function syncExternalMemory(input: {
  config: ExternalMemorySyncConfig;
  payload: ExternalMemorySyncPayload;
  fetcher?: typeof fetch;
}): Promise<ExternalMemorySyncResult> {
  const configReport = validateExternalMemorySyncConfig(input.config);
  const payloadReport = validateExternalMemorySyncPayload(input.payload);
  const validation = { valid: configReport.valid && payloadReport.valid, errors: [...configReport.errors, ...payloadReport.errors], warnings: [...configReport.warnings, ...payloadReport.warnings], summary: `${configReport.summary} ${payloadReport.summary}` };

  if (!input.config.enabled) return { status: 'disabled', accepted: false, payload: input.payload, validation, summary: 'External memory sync is disabled.' };
  if (!validation.valid) return { status: 'soft-failed', accepted: false, payload: input.payload, validation, summary: `External memory sync rejected softly: ${validation.summary}` };

  try {
    const response = await (input.fetcher ?? fetch)(buildGatewayEndpoint(input.config, '/api/sovereign-memory/sync'), { method: 'POST', headers: buildGatewayHeaders(input.config), body: JSON.stringify(input.payload) });
    if (!response.ok) return { status: 'soft-failed', accepted: false, payload: input.payload, validation, summary: `External memory gateway returned ${response.status}.` };
    const body = await response.json() as Partial<ExternalMemorySyncResponse>;
    const accepted = Boolean(body.accepted ?? body.success);
    const syncResponse: ExternalMemorySyncResponse = {
      accepted,
      success: accepted,
      imported: Number(body.imported ?? 0),
      exported: Number(body.exported ?? 0),
      rejected: Number(body.rejected ?? 0),
      summary: sanitizeText(body.summary ?? 'External memory sync completed.'),
      remotePatterns: parseRemoteItems(body.remotePatterns),
    };
    return { status: syncResponse.accepted ? 'synced' : 'soft-failed', accepted: syncResponse.accepted, payload: input.payload, response: syncResponse, validation, summary: syncResponse.summary };
  } catch (error) {
    return { status: 'soft-failed', accepted: false, payload: input.payload, validation, summary: error instanceof Error ? sanitizeText(error.message) : 'External memory sync request failed.' };
  }
}

export async function searchExternalMemory(input: {
  config: ExternalMemorySyncConfig;
  query: string;
  limit?: number;
  fetcher?: typeof fetch;
}): Promise<ExternalMemorySearchResult> {
  const validation = validateExternalMemorySyncConfig(input.config);
  const query: ExternalMemorySearchQuery = { schemaVersion: 1, client: 'sovereign-studio', redaction: 'summary-only-no-source-files', workspaceId: input.config.workspaceId, collectionName: input.config.collectionName, contributorId: input.config.contributorId, includeSharedPatterns: true, query: sanitizeText(input.query), limit: Math.max(1, Math.min(input.limit ?? 8, 50)) };
  if (!input.config.enabled) return { status: 'disabled', ok: false, query, items: [], validation, summary: 'External memory sync is disabled.' };
  if (!validation.valid) return { status: 'soft-failed', ok: false, query, items: [], validation, summary: validation.summary };
  if (!query.query.trim()) return { status: 'soft-failed', ok: false, query, items: [], validation: emptyValidation('Empty search query.'), summary: 'External memory search query is empty.' };
  try {
    const response = await (input.fetcher ?? fetch)(buildGatewayEndpoint(input.config, '/api/sovereign-memory/search'), { method: 'POST', headers: buildGatewayHeaders(input.config), body: JSON.stringify(query) });
    const body = await response.json().catch(() => ({})) as { items?: unknown; results?: unknown; summary?: string };
    const items = parseRemoteItems(body.items ?? body.results);
    return { status: response.ok ? 'ready' : 'soft-failed', ok: response.ok, query, items, validation, summary: response.ok ? sanitizeText(body.summary ?? `${items.length} remote item(s) found.`) : `External memory search returned ${response.status}.` };
  } catch (error) {
    return { status: 'soft-failed', ok: false, query, items: [], validation, summary: error instanceof Error ? sanitizeText(error.message) : 'External memory search request failed.' };
  }
}

export async function pullExternalMemoryUpdates(input: {
  config: ExternalMemorySyncConfig;
  fetcher?: typeof fetch;
}): Promise<ExternalMemoryPullUpdatesResult> {
  const validation = validateExternalMemorySyncConfig(input.config);
  if (!input.config.enabled) return { status: 'disabled', ok: false, items: [], validation, summary: 'External memory sync is disabled.' };
  if (!validation.valid) return { status: 'soft-failed', ok: false, items: [], validation, summary: validation.summary };
  try {
    const url = new URL(buildGatewayEndpoint(input.config, '/api/sovereign-memory/pull-updates'));
    url.searchParams.set('workspaceId', input.config.workspaceId);
    url.searchParams.set('collectionName', input.config.collectionName);
    url.searchParams.set('contributorId', input.config.contributorId);
    url.searchParams.set('includeSharedPatterns', 'true');
    const response = await (input.fetcher ?? fetch)(url.toString(), { headers: buildGatewayHeaders(input.config) });
    const body = await response.json().catch(() => ({})) as { items?: unknown; updates?: unknown; summary?: string };
    const items = parseRemoteItems(body.items ?? body.updates);
    return { status: response.ok ? 'ready' : 'soft-failed', ok: response.ok, items, validation, summary: response.ok ? sanitizeText(body.summary ?? `${items.length} remote update(s) available.`) : `External memory update pull returned ${response.status}.` };
  } catch (error) {
    return { status: 'soft-failed', ok: false, items: [], validation, summary: error instanceof Error ? sanitizeText(error.message) : 'External memory pull-updates request failed.' };
  }
}

export async function deleteExternalMemoryData(input: {
  config: ExternalMemorySyncConfig;
  request: ExternalMemoryDeleteRequest;
  fetcher?: typeof fetch;
}): Promise<ExternalMemoryDeleteResult> {
  const configReport = validateExternalMemorySyncConfig(input.config);
  const requestReport = validateExternalMemoryDeleteRequest(input.request);
  const validation = { valid: configReport.valid && requestReport.valid, errors: [...configReport.errors, ...requestReport.errors], warnings: [...configReport.warnings, ...requestReport.warnings], summary: `${configReport.summary} ${requestReport.summary}` };

  if (!input.config.enabled) return { status: 'disabled', deleted: false, request: input.request, validation, summary: 'External memory sync is disabled.' };
  if (!validation.valid) return { status: 'soft-failed', deleted: false, request: input.request, validation, summary: `External memory delete rejected softly: ${validation.summary}` };
  if (input.request.scope !== 'contributor-submissions' || input.request.preserveSharedPatterns !== true) {
    return { status: 'soft-failed', deleted: false, request: input.request, validation, summary: 'External memory delete blocked because it would not preserve shared patterns.' };
  }

  try {
    const response = await (input.fetcher ?? fetch)(buildGatewayEndpoint(input.config, '/api/sovereign-memory/delete-user-data'), { method: 'POST', headers: buildGatewayHeaders(input.config), body: JSON.stringify(input.request) });
    if (!response.ok) return { status: 'soft-failed', deleted: false, request: input.request, validation, summary: `External memory delete returned ${response.status}.` };
    const body = await response.json().catch(() => ({})) as Partial<ExternalMemoryDeleteResponse>;
    const deleted = Boolean(body.deleted ?? body.success);
    const deleteResponse: ExternalMemoryDeleteResponse = {
      success: deleted,
      deleted,
      deletedItems: Number(body.deletedItems ?? 0),
      retainedSharedItems: Number(body.retainedSharedItems ?? 0),
      summary: sanitizeText(body.summary ?? 'External memory contributor submissions deletion completed.'),
    };
    return { status: deleted ? 'synced' : 'soft-failed', deleted, request: input.request, response: deleteResponse, validation, summary: deleteResponse.summary };
  } catch (error) {
    return { status: 'soft-failed', deleted: false, request: input.request, validation, summary: error instanceof Error ? sanitizeText(error.message) : 'External memory delete request failed.' };
  }
}
