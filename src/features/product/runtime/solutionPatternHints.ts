import type { SolutionPattern, SolutionPatternStore } from './solutionPatternMemory';

export interface SolutionPatternHint {
  readonly visible: boolean;
  readonly title: string;
  readonly message: string;
  readonly detail: string;
  readonly activeCount: number;
  readonly selectedPatternIds: string[];
}

const SENSITIVE_RE = /\b(?:ghp_[a-z0-9_]+|github_pat_[a-z0-9_]+|sk-[a-z0-9_-]+|bearer\s+[a-z0-9._-]+|password\s*[:=]\s*\S+|token\s*[:=]\s*\S+)\b/gi;

function sanitizeText(value: string, maxLength: number): string {
  return value.replace(SENSITIVE_RE, '<redacted>').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function activePatterns(store: SolutionPatternStore): SolutionPattern[] {
  const patterns = Array.isArray(store.patterns) ? store.patterns : [];
  return patterns
    .filter((pattern) => pattern.status === 'active')
    .sort((a, b) => b.successfulUses - a.successfulUses || b.updatedAt - a.updatedAt || a.id.localeCompare(b.id));
}

function patternLine(pattern: SolutionPattern): string {
  const category = sanitizeText(pattern.category, 40);
  const extension = sanitizeText(pattern.fileExtension, 24);
  const summary = sanitizeText(pattern.solutionSummary, 120);
  return `- ${category} ${extension}: ${summary}`;
}

export function formatSolutionPatternHints(store: SolutionPatternStore, limit = 5): string {
  const selected = activePatterns(store).slice(0, Math.max(0, Math.min(10, Math.floor(limit))));
  if (selected.length === 0) return '';
  return ['Remote Aha Memory:', ...selected.map(patternLine)].join('\n');
}

export function buildSolutionPatternHint(store: SolutionPatternStore, limit = 5): SolutionPatternHint {
  const selected = activePatterns(store).slice(0, Math.max(0, Math.min(10, Math.floor(limit))));
  const activeCount = activePatterns(store).length;
  if (selected.length === 0) {
    return {
      visible: false,
      title: 'Remote Memory',
      message: 'Keine aktiven Aha-Patterns verfügbar.',
      detail: '',
      activeCount: 0,
      selectedPatternIds: [],
    };
  }

  return {
    visible: true,
    title: 'Remote Memory',
    message: `Remote Memory: ${activeCount} aktive Pattern${activeCount === 1 ? '' : 's'} verfügbar.`,
    detail: formatSolutionPatternHints(store, limit),
    activeCount,
    selectedPatternIds: selected.map((pattern) => pattern.id),
  };
}
