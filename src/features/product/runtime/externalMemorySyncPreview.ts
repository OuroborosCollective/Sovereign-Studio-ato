import type { ScanFindingRegistry } from './scanFindingRegistry';
import type { LearningMemoryStore } from './sovereignLearningMemory';
import type { SolutionPatternStore } from './solutionPatternMemory';
import {
  buildExternalMemorySyncPayload,
  validateExternalMemorySyncConfig,
  type ExternalMemorySyncConfig,
  type ExternalMemorySyncItemKind,
  type ExternalMemorySyncValidationReport,
} from './externalMemorySync';

export interface ExternalMemorySyncPreview {
  valid: boolean;
  itemCount: number;
  estimatedBytes: number;
  contributorId: string;
  workspaceId: string;
  collectionName: string;
  redaction: 'summary-only-no-source-files';
  includesRawSourceFiles: false;
  includesSessionSecret: false;
  kindCounts: Record<ExternalMemorySyncItemKind, number>;
  validation: ExternalMemorySyncValidationReport;
  summary: string;
}

function emptyKindCounts(): Record<ExternalMemorySyncItemKind, number> {
  return { 'scan-finding': 0, 'learning-pattern': 0, 'solution-pattern': 0 };
}

function sizeOf(value: unknown): number {
  return new TextEncoder().encode(JSON.stringify(value)).length;
}

export function buildExternalMemorySyncPreview(input: {
  config: ExternalMemorySyncConfig;
  scanRegistry?: ScanFindingRegistry;
  learningStore?: LearningMemoryStore;
  solutionStore?: SolutionPatternStore;
  now?: number;
}): ExternalMemorySyncPreview {
  const configReport = validateExternalMemorySyncConfig(input.config);
  const base = {
    contributorId: input.config.contributorId,
    workspaceId: input.config.workspaceId,
    collectionName: input.config.collectionName,
    redaction: 'summary-only-no-source-files' as const,
    includesRawSourceFiles: false as const,
    includesSessionSecret: false as const,
  };

  try {
    const payload = buildExternalMemorySyncPayload(input);
    const kindCounts = emptyKindCounts();
    for (const item of payload.items) kindCounts[item.kind] += 1;
    const estimatedBytes = sizeOf({ ...payload, items: payload.items.map((item) => ({ ...item, text: '<summary-preview>' })) });
    return {
      ...base,
      valid: configReport.valid,
      itemCount: payload.items.length,
      estimatedBytes,
      kindCounts,
      validation: configReport,
      summary: `${payload.items.length} sanitized item(s) ready for sync. ${estimatedBytes} estimated byte(s). Raw source files and session secrets are not included.`,
    };
  } catch (error) {
    return {
      ...base,
      valid: false,
      itemCount: 0,
      estimatedBytes: 0,
      kindCounts: emptyKindCounts(),
      validation: {
        valid: false,
        errors: [error instanceof Error ? error.message : 'Sync preview failed.'],
        warnings: configReport.warnings,
        summary: 'External memory sync preview failed.',
      },
      summary: error instanceof Error ? error.message : 'External memory sync preview failed.',
    };
  }
}
