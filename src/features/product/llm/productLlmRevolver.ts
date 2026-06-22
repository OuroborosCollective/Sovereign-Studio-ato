import type { Card, ProjectSettings } from '../types';
import type { LlmAdapter, LlmAdapterContext, LlmRevolverOptions, LlmRevolverResult } from './llmAdapter';
import { resolveWithLlmRevolver } from './llmRevolver';
import { buildSovereignLlmAdapters } from './sovereignLlmAdapters';

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
  pollinationsApiKey?: string;
  groqApiKey?: string;
  huggingfaceApiKey?: string;
  togetherApiKey?: string;
  openrouterApiKey?: string;
  geminiApiKey?: string;
  memoryContext?: string[];
  runtimeEvents?: string[];
}

export function buildProductAdapters(input: ProductLlmRevolverInput): LlmAdapter[] {
  return buildSovereignLlmAdapters({
    pollinationsApiKey: input.pollinationsApiKey,
    groqApiKey: input.groqApiKey,
    huggingfaceApiKey: input.huggingfaceApiKey,
    togetherApiKey: input.togetherApiKey,
    openrouterApiKey: input.openrouterApiKey,
    geminiApiKey: input.geminiApiKey,
    cards: input.cards,
    settings: input.settings,
  });
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
    memoryContext: input.memoryContext,
    runtimeEvents: input.runtimeEvents,
  };

  return resolveWithLlmRevolver(buildProductAdapters(input), context, options);
}
