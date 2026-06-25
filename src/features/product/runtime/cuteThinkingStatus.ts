export interface CuteThinkingFrame {
  readonly emoji: string;
  readonly text: string;
}

const IDLE_FRAME: CuteThinkingFrame = {
  emoji: '🌸',
  text: 'bereit zum Bauen',
};

export const CUTE_THINKING_FRAMES: readonly CuteThinkingFrame[] = [
  { emoji: '🤖💭', text: 'sortiere den Auftrag' },
  { emoji: '🧸✨', text: 'prüfe Repo und Kontext' },
  { emoji: '🐣🔎', text: 'suche passende Dateien' },
  { emoji: '🦊🧩', text: 'verbinde Pattern Memory' },
  { emoji: '🐙⚙️', text: 'lasse die Runtime arbeiten' },
  { emoji: '🛠️🌷', text: 'bereite echte Änderungen vor' },
  { emoji: '🧪🍬', text: 'achte auf Tests und Guards' },
  { emoji: '🚀💌', text: 'halte Draft PR als Ziel bereit' },
] as const;

export function normalizeThinkingFrameIndex(index: number, total = CUTE_THINKING_FRAMES.length): number {
  if (!Number.isFinite(index) || index < 0) return 0;
  if (!Number.isFinite(total) || total <= 0) return 0;
  return Math.floor(index) % total;
}

export function getCuteThinkingFrame(index: number, active: boolean): CuteThinkingFrame {
  if (!active) return IDLE_FRAME;
  return CUTE_THINKING_FRAMES[normalizeThinkingFrameIndex(index)] ?? IDLE_FRAME;
}

export function formatCuteThinkingLabel(args: {
  readonly index: number;
  readonly active: boolean;
  readonly status?: string;
}): string {
  const frame = getCuteThinkingFrame(args.index, args.active);
  if (!args.active) return `${frame.emoji} ${frame.text}`;
  const cleanStatus = args.status?.trim();
  const suffix = cleanStatus ? ` · ${cleanStatus}` : '';
  return `${frame.emoji} ${frame.text}...${suffix}`;
}
