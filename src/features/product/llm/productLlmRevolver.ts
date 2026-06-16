import type { Card, ProjectSettings } from '../types';
import type { LlmAdapter, LlmAdapterContext, LlmRevolverOptions, LlmRevolverResult } from './llmAdapter';
import { resolveWithLlmRevolver } from './llmRevolver';
import { createLocalSafeAdapter } from './adapters/localSafeAdapter';

export interface ProductLlmRevolverInput {
  mission: string;
  repoPaths: string[];
  selectedFilePath: string;
  cards: Card[];
  settings: ProjectSettings;
  codeContext?: string;
  logs?: string[];
  plugins?: LlmAdapter[];
  allowExternalNoKey?: boolean;
  allowOptInRoutes?: boolean;
}

export function buildProductAdapters(input: ProductLlmRevolverInput): LlmAdapter[] {
  return [
    ...(input.plugins ?? []),
    createLocalSafeAdapter({ cards: input.cards, settings: input.settings }),
  ].sort((a, b) => a.priority - b.priority);
}

export async function resolveProductWithLlmRevolver(
  input: ProductLlmRevolverInput,
  options: LlmRevolverOptions = {},
): Promise<LlmRevolverResult> {
  const context: LlmAdapterContext = {
    mission: input.mission,
    repoPaths: input.repoPaths,
    selectedFilePath: input.selectedFilePath,
    codeContext: input.codeContext,
    logs: input.logs,
    allowExternalNoKey: input.allowExternalNoKey,
    allowOptInRoutes: input.allowOptInRoutes,
  };

  return resolveWithLlmRevolver(buildProductAdapters(input), context, options);
}
