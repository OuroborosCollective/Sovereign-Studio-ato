import type { ScanFindingCategory } from './scanFindingRegistry';
import type { ExternalMemorySyncItem } from './externalMemorySync';
import {
  learnSolutionPattern,
  validateSolutionPatternStore,
  type SolutionPatternLearningInput,
  type SolutionPatternStore,
  type SolutionPatternValidationReport,
} from './solutionPatternMemory';

export interface RemoteMemoryUpdateIntakeResult {
  accepted: number;
  rejected: number;
  store: SolutionPatternStore;
  rejections: string[];
  validation: SolutionPatternValidationReport;
  summary: string;
}

const KNOWN_CATEGORIES: ScanFindingCategory[] = [
  'architecture',
  'type-error',
  'build-logic',
  'warning',
  'security-leak',
  'test-doubles',
  'build-artifact',
  'runtime-guard',
  'auth',
  'workflow',
  'ci-failure',
  'learning-memory',
  'diff-preview',
  'generated-file',
  'docs',
];

const MAX_REMOTE_UPDATES = 80;
const MAX_TEXT = 1600;
const UNSAFE_TEXT = /(password|credential|private[_-]?key)\s*[:=]\s*\S+/gi;

function sanitizeText(value = ''): string {
  return value.trim().slice(0, MAX_TEXT).replace(UNSAFE_TEXT, '<redacted-sensitive>');
}

function hasUnsafeText(value = ''): boolean {
  UNSAFE_TEXT.lastIndex = 0;
  return UNSAFE_TEXT.test(value);
}

function stringMetadata(item: ExternalMemorySyncItem, key: string): string {
  const value = item.metadata[key];
  return typeof value === 'string' ? value : '';
}

function numberMetadata(item: ExternalMemorySyncItem, key: string): number {
  const value = item.metadata[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function categoryFromRemoteItem(item: ExternalMemorySyncItem): ScanFindingCategory {
  const metadataCategory = stringMetadata(item, 'category');
  if (KNOWN_CATEGORIES.includes(metadataCategory as ScanFindingCategory)) return metadataCategory as ScanFindingCategory;
  const tagCategory = item.tags.find((tag) => KNOWN_CATEGORIES.includes(tag as ScanFindingCategory));
  return (tagCategory as ScanFindingCategory | undefined) ?? 'learning-memory';
}

function filePathFromRemoteItem(item: ExternalMemorySyncItem): string {
  const hint = stringMetadata(item, 'filePathHint');
  if (hint) return hint;
  const extension = stringMetadata(item, 'fileExtension') || '.pattern';
  return `remote/shared-solution${extension.startsWith('.') ? extension : `.${extension}`}`;
}

export function validateRemoteMemoryUpdateItem(item: ExternalMemorySyncItem): SolutionPatternValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (item.kind !== 'solution-pattern') errors.push('Only solution-pattern remote updates can become local solution patterns.');
  if (item.metadata.contributionScope !== 'shared-derived-pattern') errors.push('Remote update must be a shared-derived-pattern.');
  if (!item.id.trim()) errors.push('Remote update id is required.');
  if (!item.title.trim()) errors.push('Remote update title is required.');
  if (!item.text.trim()) errors.push('Remote update text is required.');
  if ([item.id, item.title, item.text, ...item.tags].some(hasUnsafeText)) errors.push('Remote update contains unsafe raw text.');
  if (!item.tags.length) warnings.push('Remote update has no tags.');
  if (numberMetadata(item, 'successfulUses') < 0) errors.push('Remote update successfulUses must not be negative.');

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in remote memory update item.`,
  };
}

export function buildLearningInputFromRemoteUpdate(item: ExternalMemorySyncItem, now = Date.now()): SolutionPatternLearningInput {
  const category = categoryFromRemoteItem(item);
  const filePath = filePathFromRemoteItem(item);
  const successfulUses = numberMetadata(item, 'successfulUses');
  const confidence = successfulUses > 0 ? 'reported' : 'inferred';
  return {
    intakeNode: 'learning-memory',
    processingNode: 'learning-memory',
    outputNodes: ['action-builder', 'workflow-repair-plan', 'learning-memory'],
    problem: {
      findingId: `remote:${sanitizeText(item.id)}`,
      category,
      filePath,
      description: sanitizeText(item.title),
      beforeSnippet: sanitizeText(item.title),
      contextPaths: [filePath],
      contextSignals: [...item.tags, stringMetadata(item, 'fileExtension'), category].filter(Boolean),
    },
    fix: {
      summary: sanitizeText(item.text),
      afterSnippet: sanitizeText(item.text),
      changedFiles: [filePath],
      steps: [
        'Review matching remote solution pattern.',
        sanitizeText(item.text),
        'Apply only after local runtime guards accept the generated change.',
      ],
      completed: false,
      proof: successfulUses > 0 ? `${successfulUses} remote success signal(s) reported by gateway.` : undefined,
    },
    confidence,
    tags: ['remote-update', 'shared-derived-pattern', ...item.tags],
    now,
  };
}

export function intakeRemoteMemoryUpdates(
  store: SolutionPatternStore,
  items: ExternalMemorySyncItem[],
  now = Date.now(),
): RemoteMemoryUpdateIntakeResult {
  let nextStore = store;
  const rejections: string[] = [];
  let accepted = 0;
  let rejected = 0;

  const storeValidation = validateSolutionPatternStore(store);
  if (!storeValidation.valid) {
    return {
      accepted: 0,
      rejected: items.length,
      store,
      rejections: storeValidation.errors,
      validation: storeValidation,
      summary: `Remote updates skipped because local solution pattern store is invalid: ${storeValidation.summary}`,
    };
  }

  for (const item of items.slice(0, MAX_REMOTE_UPDATES)) {
    const itemValidation = validateRemoteMemoryUpdateItem(item);
    if (!itemValidation.valid) {
      rejected += 1;
      rejections.push(`${item.id || 'remote'}: ${itemValidation.errors.join(' | ')}`);
      continue;
    }

    const learningInput = buildLearningInputFromRemoteUpdate(item, now);
    const result = learnSolutionPattern(nextStore, learningInput);
    nextStore = result.store;
    if (result.accepted) {
      accepted += 1;
    } else {
      rejected += 1;
      rejections.push(result.summary);
    }
  }

  if (items.length > MAX_REMOTE_UPDATES) {
    rejected += items.length - MAX_REMOTE_UPDATES;
    rejections.push(`Remote update intake truncated after ${MAX_REMOTE_UPDATES} item(s).`);
  }

  const validation = validateSolutionPatternStore(nextStore);
  return {
    accepted,
    rejected,
    store: nextStore,
    rejections,
    validation,
    summary: `${accepted} remote update(s) accepted, ${rejected} rejected. ${validation.summary}`,
  };
}
