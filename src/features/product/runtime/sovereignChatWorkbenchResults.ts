import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

export type SovereignChatResultCardKind = 'runtime-id' | 'changed-files' | 'draft-pr' | 'stopper' | 'completed';

export interface SovereignChatResultCard {
  readonly kind: SovereignChatResultCardKind;
  readonly title: string;
  readonly message: string;
  readonly actionLabel?: string;
  readonly actionUrl?: string;
  readonly items?: readonly string[];
}

export interface SovereignChatResultCardOptions {
  readonly maxChangedFiles?: number;
}

function safeText(value: string | undefined): string | undefined {
  const clean = value?.trim();
  return clean ? clean : undefined;
}

function safeUrl(value: string | undefined): string | undefined {
  const clean = safeText(value);
  if (!clean) return undefined;
  return /^https:\/\//i.test(clean) ? clean : undefined;
}

function changedFiles(snapshot: OpenHandsJobSnapshot, maxFiles: number): string[] {
  if (!Array.isArray(snapshot.changedFiles)) return [];
  return snapshot.changedFiles
    .filter((path) => typeof path === 'string' && path.trim().length > 0)
    .map((path) => path.trim())
    .slice(0, Math.max(1, maxFiles));
}

function extractRuntimeId(summary: string): string | undefined {
  const match = summary.match(/Runtime-ID\s+([^:\n.\s]+)/i);
  return safeText(match?.[1]);
}

function extractHttpsUrl(summary: string): string | undefined {
  const match = summary.match(/https:\/\/[^\s)]+/i);
  return safeUrl(match?.[0]?.replace(/[.,;]+$/, ''));
}

function isStopperSummary(summary: string): boolean {
  const clean = summary.toLowerCase();
  return clean.includes('blockiert') || clean.includes('fehlgeschlagen') || clean.includes('failed') || clean.includes('blocked');
}

export function deriveSovereignChatResultCards(
  snapshot: OpenHandsJobSnapshot,
  options: SovereignChatResultCardOptions = {},
): SovereignChatResultCard[] {
  if (snapshot.status === 'idle') return [];

  const cards: SovereignChatResultCard[] = [];
  const maxChangedFiles = options.maxChangedFiles ?? 6;
  const runtimeId = safeText(snapshot.openHandsId);
  const draftPrUrl = safeUrl(snapshot.draftPrUrl);
  const files = changedFiles(snapshot, maxChangedFiles);
  const hiddenFileCount = Math.max(0, (snapshot.changedFiles?.length ?? 0) - files.length);

  if (runtimeId) {
    cards.push({
      kind: 'runtime-id',
      title: 'Echte OpenHands Runtime',
      message: `Küken folgt echter Runtime-ID ${runtimeId}.`,
    });
  }

  if (files.length > 0) {
    cards.push({
      kind: 'changed-files',
      title: 'Geänderte Dateien',
      message: hiddenFileCount > 0
        ? `${files.length} Datei(en) sichtbar, ${hiddenFileCount} weitere im Detail.`
        : `${files.length} Datei(en) von OpenHands gemeldet.`,
      items: files,
    });
  }

  if (draftPrUrl) {
    cards.push({
      kind: 'draft-pr',
      title: 'Draft PR bereit',
      message: 'Küken hat den Draft PR ins Nest gelegt. Bitte prüfen, nicht automatisch mergen.',
      actionLabel: 'Draft PR öffnen',
      actionUrl: draftPrUrl,
    });
  }

  if ((snapshot.status === 'blocked' || snapshot.status === 'failed') && safeText(snapshot.lastError)) {
    cards.push({
      kind: 'stopper',
      title: snapshot.status === 'blocked' ? 'Stop-Gate blockiert' : 'Agent-Fehler',
      message: snapshot.lastError?.trim() ?? 'OpenHands meldet einen Blocker.',
    });
  }

  if (snapshot.status === 'completed' && !draftPrUrl && files.length === 0) {
    cards.push({
      kind: 'completed',
      title: 'Küken hat fertig gepiepst',
      message: 'OpenHands ist fertig, hat aber keine geänderten Dateien oder Draft PR gemeldet.',
    });
  }

  return cards;
}

export function deriveSovereignChatResultCardsFromSummary(summary: string): SovereignChatResultCard[] {
  const clean = summary.trim();
  if (!clean) return [];

  const cards: SovereignChatResultCard[] = [];
  const runtimeId = extractRuntimeId(clean);
  const draftPrUrl = extractHttpsUrl(clean);

  if (runtimeId) {
    cards.push({
      kind: 'runtime-id',
      title: 'Echte OpenHands Runtime',
      message: `Küken folgt echter Runtime-ID ${runtimeId}.`,
    });
  }

  if (draftPrUrl) {
    cards.push({
      kind: 'draft-pr',
      title: 'Draft PR bereit',
      message: 'Küken hat den Draft PR ins Nest gelegt. Bitte prüfen, nicht automatisch mergen.',
      actionLabel: 'Draft PR öffnen',
      actionUrl: draftPrUrl,
    });
  }

  if (isStopperSummary(clean) && !draftPrUrl) {
    cards.push({
      kind: 'stopper',
      title: 'Stop-Gate oder Agent-Fehler',
      message: clean,
    });
  }

  return cards;
}
