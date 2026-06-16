import { buildSovereignImplementationPackage } from '../../runtime/sovereignRuntime';
import type { Card, ProjectSettings } from '../../types';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';

export interface LocalSafeAdapterOptions {
  cards: Card[];
  settings: ProjectSettings;
}

export function createLocalSafeAdapter(options: LocalSafeAdapterOptions): LlmAdapter {
  return {
    id: 'local-safe',
    label: 'Local safe deterministic planner',
    kind: 'local-safe',
    priority: 999,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const pkg = buildSovereignImplementationPackage({
        blueprint: context.mission,
        cards: options.cards,
        settings: options.settings,
        selectedFilePath: context.selectedFilePath,
        repoPaths: context.repoPaths,
        previousPreview: context.codeContext,
      });

      return {
        providerId: 'local-safe',
        brain: pkg.brain,
        raw: JSON.stringify(pkg.brain),
      };
    },
  };
}
