/**
 * BuilderContainer Pure Helpers
 *
 * Befund A (Audit 2026-07-02): BuilderContainer.tsx grew to ~4 700 lines.
 * This file is the first extraction pass: pure, non-JSX helper functions
 * and the local types they depend on are moved here so the container can
 * import them rather than defining everything inline.
 *
 * Rules:
 * - Only pure functions and shared local types live here.
 * - No React imports, no JSX, no side effects.
 * - Each extraction is a small SEARCH/REPLACE; no full-file swap.
 *
 * Next recommended extractions (not yet done):
 * - buildChatLines, buildWorkerSystemPrompt, buildWorkerMessages,
 *   buildWorkerBlockerAnswer, composerRouteHint, palRoute
 *   (depend on more types; map those imports before moving)
 * - UI sub-components -> src/features/product/components/**
 */

import type { SovereignAgentJobSnapshot } from './sovereignAgentRuntime';
import { formatMissionPreflight, validateMissionSpecificity } from './missionValidatorRuntime';

export interface IdeaOption {
  readonly label: string;
  readonly text: string;
}

export interface ChatOutcomeHint {
  readonly kind: 'runtime' | 'files' | 'draft-pr' | 'stopper' | 'done';
  readonly text: string;
  readonly href?: string;
}

export type AgentStatus = 'idle' | 'thinking' | 'editing' | 'running' | 'error';

export function appendOption(current: string, option: IdeaOption): string {
  const clean = current.trim();
  if (!clean) return option.text;
  if (clean.includes(option.text)) return clean;
  return `${clean}\n${option.text}`;
}

export function normalizeMissionText(value: string): string {
  return value
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function collapseRepeatedAnalyzedMission(value: string): string {
  let clean = normalizeMissionText(value).replace(
    /^Ideenfabrik Auftrag:\s*Ideenfabrik Auftrag:/i,
    'Ideenfabrik Auftrag:',
  );
  const marker = '\nRepository-Kontext:';
  const firstContext = clean.indexOf(marker);
  const secondContext =
    firstContext >= 0 ? clean.indexOf(marker, firstContext + marker.length) : -1;
  if (secondContext >= 0) clean = clean.slice(0, secondContext).trim();
  return clean;
}

export function isAnalyzedMission(value: string): boolean {
  const clean = collapseRepeatedAnalyzedMission(value).toLowerCase();
  return (
    clean.startsWith('ideenfabrik auftrag:') &&
    clean.includes('repository-kontext:') &&
    clean.includes('umsetzung:')
  );
}

export function missionToWishText(value: string): string {
  const clean = collapseRepeatedAnalyzedMission(value);
  if (!clean) return '';
  if (!isAnalyzedMission(clean))
    return clean.replace(/^Ideenfabrik Auftrag:\s*/i, '').trim();
  const withoutHeader = clean.replace(/^Ideenfabrik Auftrag:\s*/i, '').trim();
  const contextIndex = withoutHeader.indexOf('\nRepository-Kontext:');
  return (
    contextIndex >= 0 ? withoutHeader.slice(0, contextIndex) : withoutHeader
  ).trim();
}

export function buildAnalyzedMission(args: {
  readonly wish: string;
  readonly repoReady: boolean;
  readonly repoReason: string;
}): string {
  const existingMission = collapseRepeatedAnalyzedMission(args.wish);
  if (isAnalyzedMission(existingMission)) return existingMission;
  const wish =
    missionToWishText(args.wish) ||
    'Verbessere das Sovereign Tool so, dass es für Nutzer klar bedienbar ist.';
  const repoState = args.repoReady
    ? 'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.'
    : `Repo-Snapshot ist noch nicht bereit: ${args.repoReason}`;
  const preflight = validateMissionSpecificity(wish);
  return [
    'Ideenfabrik Auftrag:',
    wish,
    '',
    formatMissionPreflight(preflight),
    '',
    'Repository-Kontext:',
    repoState,
    '',
    'Umsetzung:',
    '- Antworte wie ein hilfreicher No-Code-Freund: kurz, freundlich und handlungsorientiert.',
    '- Analysiere zuerst die vorhandene Repo-Struktur und betroffene Dateien.',
    '- Erzeuge echte Änderungen im passenden Codepfad oder erkläre klar, warum ein Stop-Gate blockiert.',
    '- Nutze vorhandene Pattern Memory Hinweise, wenn sie passen.',
    '- Halte Sovereign Tool getrennt von WASD/Science-Portal Drift.',
    '- Nutze Runtime-Checks, Validierungen und Tests, soweit sinnvoll.',
    '- Keine Mock-, Stub- oder Facade-Live-Pfade.',
    '- Kein Auto-Merge. Ergebnis nur als prüfbarer Draft PR oder klarer Blocker.',
  ].join('\n');
}

export function safeHttpsUrl(value: string | undefined): string | undefined {
  const clean = value?.trim();
  return clean && clean.startsWith('https://') ? clean : undefined;
}

export function splitFilePath(filePath: string | undefined): {
  path?: string;
  file?: string;
} {
  const clean = filePath?.trim();
  if (!clean) return {};
  const slash = clean.lastIndexOf('/');
  if (slash < 0) return { file: clean };
  return { path: `${clean.slice(0, slash + 1)}`, file: clean.slice(slash + 1) };
}

export function buildOutcomeHints(
  job: SovereignAgentJobSnapshot | undefined,
): ChatOutcomeHint[] {
  if (!job || job.status === 'idle') return [];
  const hints: ChatOutcomeHint[] = [];
  const files = (job.changedFiles ?? [])
    .filter((f) => typeof f === 'string' && f.trim())
    .map((f) => f.trim());
  const draftPrUrl = safeHttpsUrl(job.draftPrUrl);
  if (job.runtimeId?.trim())
    hints.push({ kind: 'runtime', text: `🐤 Sovereign Agent ID: ${job.runtimeId.trim()}` });
  if (files.length > 0)
    hints.push({ kind: 'files', text: `${files.length} Datei(en) geändert · Details im Files-Menü` });
  if (draftPrUrl)
    hints.push({ kind: 'draft-pr', text: 'Draft PR bereit · Öffnen', href: draftPrUrl });
  if ((job.status === 'blocked' || job.status === 'failed') && job.lastError?.trim())
    hints.push({ kind: 'stopper', text: job.lastError.trim() });
  if (job.status === 'completed' && files.length === 0 && !draftPrUrl)
    hints.push({ kind: 'stopper', text: 'Sovereign Agent meldet abgeschlossen, aber keine Dateiänderung und kein Draft PR sind belegt' });
  return hints;
}

export function deriveAgentStatus(args: {
  readonly repoBusy: boolean;
  readonly runtimeBusy: boolean;
  readonly isPublishing: boolean;
  readonly agentIsRunning?: boolean;
  readonly agentJob?: SovereignAgentJobSnapshot;
  readonly localRepoLoading: boolean;
  readonly localRepoError: boolean;
}): AgentStatus {
  if (
    args.localRepoError ||
    args.agentJob?.status === 'failed' ||
    args.agentJob?.status === 'blocked'
  )
    return 'error';
  if (args.isPublishing || args.agentJob?.status === 'running') return 'running';
  if (
    (args.agentJob?.changedFiles?.length ?? 0) > 0 ||
    Boolean(args.agentJob?.draftPrUrl)
  )
    return 'editing';
  if (
    args.localRepoLoading ||
    args.agentIsRunning ||
    args.repoBusy ||
    args.runtimeBusy
  )
    return 'thinking';
  return 'idle';
}

export function fmtTime(ts: number): string {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
