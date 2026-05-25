import type { Card, FileItem, ProjectSettings } from './types';

export const makeId = () => crypto.randomUUID();

export const demoFiles: FileItem[] = [
  { path: 'src/App.tsx', icon: '🟦' },
  { path: 'src/main.tsx', icon: '🟦' },
  { path: 'package.json', icon: '📦' },
  { path: 'pnpm-workspace.yaml', icon: '🧩' },
  { path: '.github/workflows/ci.yml', icon: '⚙️' },
  { path: 'android/app/build.gradle', icon: '🤖' },
];

export const starterCards = (): Card[] => [
  { id: makeId(), title: '1 · Wunsch', body: 'User beschreibt das gewünschte Produkt oder Feature in natürlicher Sprache.' },
  { id: makeId(), title: '2 · Repo lesen', body: 'Dateibaum, Struktur, Workflows und wichtige Dateien werden als Kontext genutzt.' },
  { id: makeId(), title: '3 · Code erzeugen', body: 'Der Agent wechselt in den Editor und schreibt sichtbaren Code in Dateien.' },
  { id: makeId(), title: '4 · Publish & Validate', body: 'Push/PR wird vorbereitet, Workflows werden geprüft, Fehler springen zurück in den Editor.' },
];

export const defaultSettings: ProjectSettings = {
  repoMode: 'monorepo',
  packageManager: 'pnpm',
  installStrategy: 'workspace',
  linter: 'auto',
  specialization: 'React/Vite + Capacitor Android + GitHub Actions Release Pipeline',
  maxFixLoops: 3,
};
