import type { Card, FileItem, ProjectSettings } from './types';

export const makeId = () => crypto.randomUUID();

export const demoFiles: FileItem[] = [
  { path: 'src/App.tsx', icon: 'TS' },
  { path: 'src/main.tsx', icon: 'TS' },
  { path: 'src/features/product/freeFirstPlan.ts', icon: 'PLAN' },
  { path: 'package.json', icon: 'PKG' },
  { path: 'pnpm-workspace.yaml', icon: 'WS' },
  { path: '.github/workflows/ci.yml', icon: 'CI' },
  { path: 'android/app/build.gradle', icon: 'APK' },
];

export const starterCards = (): Card[] => [
  { id: makeId(), title: '1 Wunsch', body: 'User beschreibt das Produkt in natuerlicher Sprache.' },
  { id: makeId(), title: '2 Free Route', body: 'No-key Anbieter zuerst, eigene Keys nur optional.' },
  { id: makeId(), title: '3 Code', body: 'Der Agent schreibt sichtbaren Code in Dateien.' },
  { id: makeId(), title: '4 Validate', body: 'Workflow Fehler springen zurueck in den Editor.' },
];

export const defaultSettings: ProjectSettings = {
  repoMode: 'monorepo',
  packageManager: 'pnpm',
  installStrategy: 'workspace',
  linter: 'auto',
  specialization: 'React Vite Capacitor Android GitHub Actions Free First Router',
  maxFixLoops: 3,
};
