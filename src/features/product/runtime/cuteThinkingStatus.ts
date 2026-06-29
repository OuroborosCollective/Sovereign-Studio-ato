export interface CuteThinkingFrame {
  readonly emoji: string;
  readonly text: string;
}

const IDLE_FRAME: CuteThinkingFrame = {
  emoji: '🌸',
  text: 'bereit zum Bauen',
};

const DONE_FRAME: CuteThinkingFrame = {
  emoji: '🐤✅',
  text: 'Küken hat fertig gepiepst',
};

const CUTE_THINKING_EMOJIS = [
  '🤖💭',
  '🧸✨',
  '🐣🔎',
  '🐤🌾',
  '🐥💛',
  '🐤🐾',
  '🐣🧠',
  '🐥🛠️',
  '🦊🧩',
  '🐙⚙️',
  '🛠️🌷',
  '🧪🍬',
  '🚀💌',
] as const;

const CUTE_CHICK_THINKING_TEXTS = [
  'Küken piepst und sortiert den Auftrag',
  'Küken sucht Körner im Repo',
  'Piep piep, ich prüfe echte Dateien',
  'Küken pickt passende Pattern heraus',
  'Küken schreibt vorsichtig Code',
  'Piep, ich lasse die Runtime arbeiten',
  'Küken schaut nach Tests und Guards',
  'Küken hält den Draft PR warm',
  'Piep, ich suche keinen Fake-Fortschritt',
  'Küken schnäbelt durch die Logs',
  'Küken klopft sanft an OpenHands',
  'Küken sortiert Diff-Krümel',
  'Küken zählt keine Fake-Prozente',
  'Piep, ich verbinde Chat und Runtime',
  'Küken hat gleich fertig gepiepst',
] as const;

const WORKING_STATUS_TEXTS = [
  'Küken piepst ... ich arbeite',
  'Küken sucht Körner ... Piep',
  'Küken schreibt Code ... Piep Piep',
  'Küken pickt echte Änderungen heraus',
  'Piep ... ich sortiere Dateien und Tests',
] as const;

const DONE_STATUS_TEXTS = [
  'Küken hat fertig gepiepst',
  'Piep, Ergebnis ist prüfbar',
  'Küken legt das Ergebnis ins Nest',
] as const;

const IDLE_STATUS_TEXTS = [
  'idle · warte auf den nächsten echten Schritt',
  'idle · halte die Runtime ruhig bereit',
  'idle · beobachte Repo, Auftrag und Gates',
  'idle · kein Live-Pfad läuft gerade',
  'idle · bereit für eine echte Aktion',
] as const;

export const CUTE_WORKSTATE_DOT_FRAMES = ['...', '..', '.'] as const;

export const CUTE_KAOMOJI_FRAMES = [
  '(^_^)',
  '(^o^)',
  '＼(^^)／',
  '＼(^-^)／',
  '＼(^_^)／',
  '(^ー^)',
  '(^○^)',
  '(￣ー￣)',
  '(⌒‐⌒)',
  'd=(^o^)=b',
  'o(^o^)o',
  'p(^^)q',
  'p(^-^)q',
  '( ﾟーﾟ)',
  '(　＾∀＾)',
  '(　＾▽＾)',
  '( ＾ω＾ )',
  '(　＾ω＾)',
  '(　＾Д＾)',
  '( ´;ﾟ;∀;ﾟ;)',
  '( ´,_ゝ`)',
  '( ￣▽￣)',
  '( ￣ー￣)',
  '( ´ー`)',
  '( ´∀｀ )b',
  '( ´∀`)',
  '( ´・∀・｀)',
  '(*^ー^)ノ♪',
  '(*ﾟ∀ﾟ人ﾟ∀ﾟ*)♪',
  '(*≧∀≦)',
  '(￣▽￣)',
  '(ﾟ∀ﾟ 三 ﾟ∀ﾟ)',
  '(o^－^o)',
  'ヽ(´∀｀≡´∀｀)ﾉ',
  'Ｏ(≧∇≦)Ｏ',
  '((T_T))',
  '( ｡ﾟДﾟ｡)',
  '( ´-｀)',
  '(´・c_・`)',
  '゜゜(´O｀)°゜',
  'Σ(＞Д＜)',
  '(@_@)',
  '(@_@;)',
  '(￣O￣)',
  '(ノ゜ο゜)ノ',
  '(ﾟДﾟ≡ﾟДﾟ)ﾞ?',
  'Σヽ(ﾟ∀ﾟ；)',
  '＼(◎o◎)／',
  '(・・;)',
  '(^_^;)',
  '( ;´･ω･`)',
  '(  -_・)?',
  '(;＞_＜;)',
  '( ;｀Д´)',
  '(ノ-_-)ノ~┻━┻',
  '(Ｏﾟ皿ﾟＯ)',
  '(*｀ω´*)',
  '(＃ﾟДﾟ)ﾉ',
  '(((￣へ￣井)',
  '(ー。ー#)',
  '(｡-｀へ´-｡)',
  '(⌒0⌒)／~~',
  '(-_-)/~~~',
  '(＠＾＾＠)／',
  '(* ´ ▽ ` *)ﾉ',
  '(*^ーﾟ)ﾉ',
  '(^ー゜)ノ',
  '(*￣▽￣)ノ~~ ♪',
  '(^人^)',
  '((φ(￣ー￣  )',
  '(-.-)y-~',
  '(-。-)y-~',
  '(;_;)/~~~',
  '(-.-)ノ⌒-~',
  '(。-_-。)♪',
  'φ(．．)',
  '(/--)/',
  '(^з^)-☆',
  '(〃´ー｀人´ー｀〃)',
  'ヽ(●´ε｀●)ノ',
  'ヽ(o´3`o)ﾉ',
  '( ﾟ∀ﾟ)人(ﾟ∀ﾟ )',
  '(^3^)/',
  '(*⌒３⌒*)',
  '(≡・x・≡)',
  '(=^ェ^=)',
  '(-)_(-)',
  '(ФωФ)',
  'U^ェ^U',
  '⌒(ё)⌒',
  '￣(=∵=)￣',
] as const;

export const CUTE_THINKING_FRAMES: readonly CuteThinkingFrame[] = CUTE_CHICK_THINKING_TEXTS.map((text, index) => ({
  emoji: CUTE_THINKING_EMOJIS[index % CUTE_THINKING_EMOJIS.length],
  text,
}));

function deterministicCutePick(index: number, total: number, salt = 0): number {
  if (!Number.isFinite(index) || index < 0) return 0;
  if (!Number.isFinite(total) || total <= 0) return 0;
  const seed = Math.floor(index) + salt * 97;
  return Math.abs((seed * 1103515245 + 12345) >>> 0) % total;
}

function statusSalt(status?: string): number {
  if (!status) return 1;
  return [...status].reduce((sum, char) => sum + char.charCodeAt(0), 7);
}

function isDoneStatus(status?: string): boolean {
  const clean = status?.toLowerCase() ?? '';
  return ['done', 'fertig', 'completed', 'complete', 'success', 'draft pr', 'green'].some((token) => clean.includes(token));
}

function isWorkingStatus(status?: string): boolean {
  const clean = status?.toLowerCase() ?? '';
  return ['working', 'arbeitet', 'running', 'schreibt', 'code', 'build', 'package', 'agent'].some((token) => clean.includes(token));
}

export function normalizeThinkingFrameIndex(index: number, total = CUTE_THINKING_FRAMES.length): number {
  if (!Number.isFinite(index) || index < 0) return 0;
  if (!Number.isFinite(total) || total <= 0) return 0;
  return Math.floor(index) % total;
}

export function getCuteThinkingFrame(index: number, active: boolean, status?: string): CuteThinkingFrame {
  if (!active) return IDLE_FRAME;
  if (isDoneStatus(status)) return DONE_FRAME;
  if (isWorkingStatus(status)) {
    const text = WORKING_STATUS_TEXTS[deterministicCutePick(index, WORKING_STATUS_TEXTS.length, statusSalt(status))] ?? WORKING_STATUS_TEXTS[0];
    return {
      emoji: CUTE_THINKING_EMOJIS[deterministicCutePick(index, CUTE_THINKING_EMOJIS.length, statusSalt(text))] ?? '🐤',
      text,
    };
  }
  return CUTE_THINKING_FRAMES[normalizeThinkingFrameIndex(index)] ?? IDLE_FRAME;
}

export function getCuteKaomojiFrame(index: number, salt = 0): string {
  return CUTE_KAOMOJI_FRAMES[deterministicCutePick(index, CUTE_KAOMOJI_FRAMES.length, salt)] ?? CUTE_KAOMOJI_FRAMES[0];
}

export function getCuteWorkStateDotFrame(index: number): string {
  return CUTE_WORKSTATE_DOT_FRAMES[normalizeThinkingFrameIndex(index, CUTE_WORKSTATE_DOT_FRAMES.length)] ?? CUTE_WORKSTATE_DOT_FRAMES[0];
}

function getIdleStatusText(index: number, status?: string): string {
  const cleanStatus = status?.trim();
  if (cleanStatus) return cleanStatus;
  return IDLE_STATUS_TEXTS[deterministicCutePick(index, IDLE_STATUS_TEXTS.length, 23)] ?? IDLE_STATUS_TEXTS[0];
}

export function formatCuteWorkStateLabel(args: {
  readonly index: number;
  readonly active: boolean;
  readonly status?: string;
}): string {
  const frame = getCuteThinkingFrame(args.index, args.active, args.status);
  const dotTrail = getCuteWorkStateDotFrame(args.index);
  const salt = statusSalt(`${frame.text}:${args.status ?? ''}:workstate`);
  const primaryKaomoji = getCuteKaomojiFrame(args.index, salt);
  const secondaryKaomoji = getCuteKaomojiFrame(args.index + 3, salt + 13);
  const kaomoji = args.index % 2 === 0 ? `${primaryKaomoji} ${secondaryKaomoji}` : primaryKaomoji;

  if (!args.active) {
    return `${frame.emoji} ${kaomoji}${dotTrail} ${getIdleStatusText(args.index, args.status)}`;
  }

  const cleanStatus = args.status?.trim();
  const suffix = cleanStatus ? ` · ${cleanStatus}` : '';
  return `${frame.emoji} ${kaomoji}${dotTrail} ${frame.text}${suffix}`;
}

export function formatCuteThinkingLabel(args: {
  readonly index: number;
  readonly active: boolean;
  readonly status?: string;
}): string {
  const frame = getCuteThinkingFrame(args.index, args.active, args.status);
  const salt = statusSalt(`${frame.text}:${args.status ?? ''}`);
  const primaryKaomoji = getCuteKaomojiFrame(args.index, salt);
  const secondaryKaomoji = args.index % 2 === 0 ? ` ${getCuteKaomojiFrame(args.index + 3, salt + 13)}` : '';
  const kaomoji = `${primaryKaomoji}${secondaryKaomoji}`.trim();
  if (!args.active) return `${frame.emoji} ${kaomoji} ${frame.text}`;
  const cleanStatus = args.status?.trim();
  const suffix = cleanStatus ? ` · ${cleanStatus}` : '';
  return `${frame.emoji} ${kaomoji} ${frame.text}...${suffix}`;
}
