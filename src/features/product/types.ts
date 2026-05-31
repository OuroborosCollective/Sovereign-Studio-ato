export type FileItem = { path: string; icon: string };
export type Card = { id: string; title: string; body: string };
export type WorkView = 'editor' | 'pipeline' | 'canvas';
export type PipelineState = 'idle' | 'publishing' | 'validating' | 'failed' | 'patching' | 'green';
export type ProjectSettings = {
  repoMode: 'single' | 'monorepo';
  packageManager: 'auto' | 'npm' | 'pnpm' | 'yarn' | 'bun';
  installStrategy: 'safe' | 'workspace' | 'frozen';
  linter: 'auto' | 'eslint' | 'biome' | 'prettier-eslint';
  specialization: string;
  maxFixLoops: number;
};
