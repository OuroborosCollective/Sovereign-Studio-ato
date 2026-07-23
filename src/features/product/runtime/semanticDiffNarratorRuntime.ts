import type { GeneratedFileDiffItem } from './generatedFileDiffPreview';

export interface SemanticDiffNarration {
  path: string;
  sentence: string;
  source: 'deterministic' | 'model';
}

export interface SemanticNarrationModel {
  narrate(items: readonly GeneratedFileDiffItem[]): Promise<readonly SemanticDiffNarration[]>;
}

function deterministicSentence(item: GeneratedFileDiffItem): string {
  if (item.kind === 'created') {
    return `Creates ${item.path} with ${item.newLineCount} lines.`;
  }
  if (item.kind === 'unchanged') {
    return `Leaves ${item.path} unchanged.`;
  }
  if (item.kind === 'source-missing') {
    return `Cannot describe ${item.path} semantically because its source snapshot is missing.`;
  }
  const direction = item.newLineCount >= item.oldLineCount ? 'expands' : 'reduces';
  return `${direction[0].toUpperCase()}${direction.slice(1)} ${item.path} from ${item.oldLineCount} to ${item.newLineCount} lines.`;
}

export function buildDeterministicNarrations(
  items: readonly GeneratedFileDiffItem[],
): SemanticDiffNarration[] {
  return items.map((item) => ({
    path: item.path,
    sentence: deterministicSentence(item),
    source: 'deterministic',
  }));
}

export async function narrateDiffItems(
  items: readonly GeneratedFileDiffItem[],
  model?: SemanticNarrationModel,
): Promise<SemanticDiffNarration[]> {
  if (!model) return buildDeterministicNarrations(items);
  const result = await model.narrate(items);
  const byPath = new Map(result.map((entry) => [entry.path, entry]));
  return items.map((item) => byPath.get(item.path) ?? {
    path: item.path,
    sentence: deterministicSentence(item),
    source: 'deterministic',
  });
}
